import pytest
np = pytest.importorskip("numpy", reason="install the embeddings extra for vector tests")
from watchlist.entities import Entity,Alias
from watchlist.matching_embeddings import rank_vectors,unit_vectors


def entity(eid,*names):
    return Entity(eid,names[0],'organisation',tuple(Alias(eid+str(i),n) for i,n in enumerate(names)),True,'fictional')


def test_hand_cosine_grouping_and_original_evidence():
    es=[entity('a','Moon','قمر'),entity('b','Sun')]
    rows=rank_vectors(np.array([[1,2]]),np.array([[2,1],[2,4],[-1,-2]]),es)
    assert [c.entity_id for c in rows]==['a','b']
    assert rows[0].similarity_score==pytest.approx(1)
    assert rows[0].matched_alias=='قمر'
    assert rows[1].similarity_score==pytest.approx(-1)
    assert rank_vectors(np.array([[1,2]]),np.array([[2,1]]),[entity('c','C')])[0].similarity_score==pytest.approx(.8)


def test_ties_and_dimension_errors():
    rows=rank_vectors(np.array([[1,0]]),np.array([[1,0],[1,0]]),[entity('b','B'),entity('a','A')])
    assert [c.entity_id for c in rows]==['a','b']
    with pytest.raises(ValueError,match='dimension'):
        rank_vectors(np.array([[1,0,0]]),np.array([[1,0]]),[entity('a','A')])
    with pytest.raises(ValueError,match='duplicate'):
        rank_vectors(np.array([[1,0]]),np.array([[1,0],[1,0]]),[entity('a','A'),entity('a','A')])


@pytest.mark.parametrize('values',[[[0,0]],[[float('nan'),1]],[[float('inf'),0]],[1,2]])
def test_invalid_vectors(values):
    with pytest.raises(ValueError):unit_vectors(np.array(values))


@pytest.mark.parametrize('k',[0,True,-1,1.2])
def test_invalid_k(k):
    with pytest.raises(ValueError):rank_vectors(np.array([[1,0]]),np.array([[1,0]]),[entity('a','A')],k)
