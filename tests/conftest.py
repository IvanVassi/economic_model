import sys, warnings
import pytest
sys.path.insert(0, '/Users/ivan/code/model')
warnings.filterwarnings('ignore')
from mdn import load
from sim import Model, Semantics

MDN = '/Users/ivan/code/model/SNHM.MDN'


@pytest.fixture(scope='session')
def blocks():
    return load(MDN)


@pytest.fixture(scope='session')
def model(blocks):
    return Model(blocks, Semantics())


@pytest.fixture(scope='session')
def settled(model):
    v = model.initial_state('saved')
    model.settle(v, iters=150)
    return v
