"""Parse the reviewed current SDN XML name profile offline."""

from __future__ import annotations

import hashlib
import io
import re
import stat
import struct
from xml.etree import ElementTree
import zipfile
import zlib

from watchlist.ingest._parse_common import (
    alias_evidence,
    check_schema_version,
    children,
    expanded_tag,
    field_text,
    finish,
    identifier,
    node_text,
    one,
    source_record,
    unique_identifier,
    utf8_text,
    validate_payload,
    xml_language,
    xml_root,
)
from watchlist.ingest.source_registry import (
    AliasEvidence,
    ParseContext,
    ParseResult,
    SourceValidationError,
)


PARSER_VERSION = "ofac-sdn-non-person-v1"
NAMESPACE = (
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"
)
ELIGIBLE_TYPES = {"Entity": "organization", "Vessel": "vessel"}
ZIP_MEMBER = "SDN.XML"
MAX_DECODED_BYTES = 32_000_000
DECODE_CHUNK_BYTES = 64 * 1024


def _zip_member(payload: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    """Validate one flat ordinary ZIP member without trusting declared sizes.

    Central and local headers must agree, and the compressed bytes must occupy
    exactly their declared region. ZIP64, split archives and hidden extra data
    are outside this deliberately small profile.
    """
    if len(payload) < 22 or payload[-22:-18] != b"PK\x05\x06":
        raise SourceValidationError(
            "OFAC ZIP requires a complete, uncommented archive."
        )
    (
        _,
        disk,
        directory_disk,
        disk_entries,
        entries,
        directory_size,
        directory_offset,
        comment,
    ) = struct.unpack("<4s4H2IH", payload[-22:])
    if (
        disk != 0
        or directory_disk != 0
        or disk_entries != 1
        or entries != 1
        or comment != 0
        or directory_offset < 30
        or directory_offset + directory_size != len(payload) - 22
        or directory_size < 46
        or payload[directory_offset : directory_offset + 4] != b"PK\x01\x02"
    ):
        raise SourceValidationError(
            "OFAC ZIP must contain one complete, unsplit member."
        )
    name_length, extra_length, comment_length = struct.unpack_from(
        "<3H", payload, directory_offset + 28
    )
    if directory_size != 46 + name_length + extra_length + comment_length or payload[
        directory_offset + 46 : directory_offset + 46 + name_length
    ] != ZIP_MEMBER.encode("ascii"):
        raise SourceValidationError(
            "OFAC ZIP central directory has unexpected content."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise SourceValidationError(
                    "OFAC ZIP must contain exactly one XML member."
                )
            member = members[0]
    except (zipfile.BadZipFile, ValueError, NotImplementedError, OSError) as exc:
        raise SourceValidationError("Malformed OFAC ZIP directory.") from exc
    if (
        member.filename != ZIP_MEMBER
        or member.header_offset != 0
        or member.is_dir()
        or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
        or member.flag_bits & ~0x080E
        or (member.compress_type == zipfile.ZIP_STORED and member.flag_bits & 0x0006)
        or member.extract_version > 20
        or stat.S_IFMT(member.external_attr >> 16) not in {0, stat.S_IFREG}
        or member.external_attr & 0x10
        or not 1 <= member.file_size <= MAX_DECODED_BYTES
        or not 1 <= member.compress_size <= len(payload)
    ):
        raise SourceValidationError(
            "Unsupported, nonregular or oversized OFAC ZIP member."
        )
    if len(payload) < 30:
        raise SourceValidationError("Truncated OFAC ZIP local header.")
    (
        signature,
        version,
        flags,
        method,
        _,
        _,
        crc,
        compressed,
        decoded,
        name_length,
        extra_length,
    ) = struct.unpack_from("<4s5H3I2H", payload)
    data_start = 30 + name_length + extra_length
    data_end = data_start + member.compress_size
    if (
        signature != b"PK\x03\x04"
        or version != member.extract_version
        or flags != member.flag_bits
        or method != member.compress_type
        or payload[30 : 30 + name_length] != ZIP_MEMBER.encode("ascii")
        or data_start > directory_offset
        or data_end > directory_offset
    ):
        raise SourceValidationError("OFAC ZIP local and central headers disagree.")
    expected = (member.CRC, member.compress_size, member.file_size)
    if flags & 0x0008:
        if any(
            actual not in {0, known}
            for actual, known in zip((crc, compressed, decoded), expected)
        ):
            raise SourceValidationError(
                "OFAC ZIP descriptor sizes conflict with its headers."
            )
        descriptor = payload[data_end:directory_offset]
        if descriptor.startswith(b"PK\x07\x08"):
            descriptor = descriptor[4:]
        if len(descriptor) != 12 or struct.unpack("<3I", descriptor) != expected:
            raise SourceValidationError("Invalid OFAC ZIP data descriptor.")
    elif (crc, compressed, decoded) != expected or data_end != directory_offset:
        raise SourceValidationError(
            "OFAC ZIP contains conflicting sizes or extra data."
        )
    return member, payload[data_start:data_end]


def _decode_zip_xml(payload: bytes) -> bytes:
    """Stream the actual DEFLATE output under both declared and absolute bounds."""
    member, encoded = _zip_member(payload)
    decoded = bytearray()
    decoder = (
        zlib.decompressobj(-zlib.MAX_WBITS)
        if member.compress_type == zipfile.ZIP_DEFLATED
        else None
    )
    try:
        for offset in range(0, len(encoded), DECODE_CHUNK_BYTES):
            pending = encoded[offset : offset + DECODE_CHUNK_BYTES]
            while pending:
                block = (
                    decoder.decompress(
                        pending,
                        min(DECODE_CHUNK_BYTES, member.file_size - len(decoded) + 1),
                    )
                    if decoder is not None
                    else pending
                )
                decoded.extend(block)
                if len(decoded) > member.file_size or len(decoded) > MAX_DECODED_BYTES:
                    raise SourceValidationError(
                        "OFAC ZIP actual decoded content exceeds its bound."
                    )
                if decoder is None:
                    break
                if decoder.unused_data:
                    raise SourceValidationError(
                        "OFAC ZIP member has trailing compressed data."
                    )
                pending = decoder.unconsumed_tail
        if decoder is not None and not decoder.eof:
            raise SourceValidationError("Truncated OFAC ZIP compressed stream.")
    except zlib.error as exc:
        raise SourceValidationError("Invalid OFAC ZIP compressed stream.") from exc
    if len(decoded) != member.file_size or zlib.crc32(decoded) != member.CRC:
        raise SourceValidationError("OFAC ZIP decoded size or CRC does not match.")
    return bytes(decoded)


def _uid(node: ElementTree.Element, seen: set[str] | None = None) -> str:
    if "uid" in node.attrib:
        raise SourceValidationError("Current OFAC profile requires child uid fields.")
    raw = field_text(node, "uid")
    value = identifier(raw) if seen is None else unique_identifier(raw, seen)
    if not re.fullmatch(r"[0-9]+", value):
        raise SourceValidationError("OFAC uid must contain ASCII digits only.")
    return value


def _name_attributes(
    node: ElementTree.Element, fields: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    """Preserve present name-part or qualifier fields, including empty strings."""
    attributes = []
    for field in fields:
        child = one(node, field, required=False)
        if child is not None:
            attributes.append((field, node_text(child, field, required=False) or ""))
    return tuple(attributes)


def parse_ofac(payload: bytes, *, context: ParseContext) -> ParseResult:
    """Use explicit SDN types and retain alias IDs, categories and type labels.

    ``lastName`` contains the source name for non-person SDN entries. Optional
    ``firstName`` text remains name-part metadata; it is not concatenated into a
    new name. Current XML uses the reviewed HTTPS namespace and child UID fields.
    Unreviewed namespaces and OFAC's distinct advanced format are unsupported.
    """
    validate_payload(payload, context, "ofac_sdn")
    decoded_xml = _decode_zip_xml(payload) if payload.startswith(b"PK") else None
    text = utf8_text(payload if decoded_xml is None else decoded_xml)
    root = xml_root(text, root_name="sdnList", namespaces=frozenset({NAMESPACE}))
    namespace = expanded_tag(root.tag)[0]
    check_schema_version(root)
    if any(
        expanded_tag(child.tag)[1] not in {"publshInformation", "sdnEntry"}
        for child in root
    ):
        raise SourceValidationError("Unsupported OFAC top-level XML structure.")
    publication = one(root, "publshInformation")
    version = field_text(publication, "Publish_Date", required=False)
    count = field_text(publication, "Record_Count", required=False)
    if count is not None and (not re.fullmatch(r"[0-9]+", count) or len(count) > 9):
        raise SourceValidationError(
            "OFAC Record_Count must be a bounded unsigned integer."
        )
    entries = children(root, "sdnEntry")
    if count is not None and int(count) != len(entries):
        raise SourceValidationError(
            "OFAC Record_Count does not match the complete payload."
        )
    seen: set[str] = set()
    records = []
    excluded_people = excluded_other = 0
    for entry in entries:
        provider_id = _uid(entry, seen)
        entry_type = field_text(entry, "sdnType")
        if entry_type == "Individual":
            excluded_people += 1
            continue
        if entry_type not in ELIGIBLE_TYPES:
            excluded_other += 1
            continue
        primary_node = one(entry, "lastName")
        primary = node_text(primary_node, "lastName")
        evidence = [
            alias_evidence(
                primary,
                "sdnEntry.lastName",
                context,
                language=xml_language(primary_node, entry, root),
                attributes=_name_attributes(entry, ("firstName",)),
            )
        ]
        aka_list = one(entry, "akaList", required=False)
        alias_ids: dict[str, AliasEvidence] = {}
        if aka_list is not None:
            if any(expanded_tag(child.tag)[1] != "aka" for child in aka_list):
                raise SourceValidationError("Unsupported OFAC alias structure.")
            for alias in aka_list:
                alias_id = _uid(alias)
                one(alias, "type")
                one(alias, "category")
                qualifiers = _name_attributes(alias, ("type", "category"))
                name_node = one(alias, "lastName", required=False)
                name = node_text(name_node, "lastName", required=False)
                name_field = "lastName"
                part_fields = ("firstName",)
                if name is None:
                    name_node = one(alias, "firstName", required=False)
                    name = node_text(name_node, "firstName", required=False)
                    name_field = "firstName"
                    part_fields = ("lastName",)
                name_parts = _name_attributes(alias, part_fields)
                if name is None:
                    continue
                parsed_alias = alias_evidence(
                    name,
                    f"sdnEntry.akaList.aka.{name_field}",
                    context,
                    language=xml_language(name_node, alias, aka_list, entry, root),
                    attributes=(("uid", alias_id),) + qualifiers + name_parts,
                )
                if alias_id in alias_ids and alias_ids[alias_id] != parsed_alias:
                    raise SourceValidationError(
                        "Conflicting OFAC evidence for one alias uid."
                    )
                alias_ids[alias_id] = parsed_alias
                evidence.append(parsed_alias)
        records.append(
            source_record(
                context,
                provider_id=provider_id,
                entity_type=ELIGIBLE_TYPES[entry_type],
                primary_name=primary,
                aliases=evidence,
                provider_schema=f"{namespace}#sdnList.sdnEntry:{entry_type}",
            )
        )
    return finish(
        payload,
        context,
        records,
        input_records=len(entries),
        excluded_person_records=excluded_people,
        excluded_other_records=excluded_other,
        parser_version=PARSER_VERSION,
        source_version=version,
        source_version_field="sdnList.publshInformation.Publish_Date"
        if version is not None
        else None,
        container_format="zip" if decoded_xml is not None else None,
        container_member=ZIP_MEMBER if decoded_xml is not None else None,
        decoded_bytes=len(decoded_xml) if decoded_xml is not None else None,
        decoded_sha256=hashlib.sha256(decoded_xml).hexdigest()
        if decoded_xml is not None
        else None,
    )
