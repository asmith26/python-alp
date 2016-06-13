import copy

import dill
import h5py
import numpy as np

from ..appcom import _path_h5
from ..celapp import app
from ..dbbackend import _path_abstract
from theano.misc.pkl_utils import dump


COMPILED_MODELS = dict()
TO_SERIALIZE = ['custom_objects']
dill.settings['recurse'] = True


def save_element(elem, filepath):
    """ Dumps the attributes of the (generally fitted) model
        in a h5 file.

    Args:
        elem(theano graph): grpah to be saved.
        filepath(string): the file name where the attributes should be written.
    """
    with open(filepath, 'wb') as f:
        dump((elem), f)


def load_elem(filepath):
    """ Load the attributes that have been dumped in a h5 file in a model.

    Args:
        model(sklearn.BaseEstimator): a sklearn model (in SUPPORTED).
        filepath(string): the file name where the attributes should be read.
    Returns:
        the model with updated parameters.
    """

    with open(filepath, 'rb') as f:
        elem = load(f)
    return elem


def normalize_name(var, key, rep):
    """Adds a name to a theano variable or function if it's not present

    Args:
        var(a theano var or function): the function to be checked
        key(str): a key to contruct the name
        rep(int): an integer to differentiate object with duplicated name"""

    # TODO: Check for another way of numbering the var names
    if var.name is None:
        var.name = '{}_{}'.format(key, rep)
        rep += 1
    return var, rep


def normalize_ordered_dict(ordered_dict):
    base = 0
    dict_mapping = dict()
    for key, var in ordered_dict.items():
        ordered_dict[key], base = normalize_name(var, key, base)
    return ordered_dict


def dump_dict(ordered_dict):
    key_name = dict()
    for k, v in ordered_dict:
        save_element(v, _path_abstract + k)
        key_name[k] = path + k
    return key_name


def load_dict(ordered_dict):
    key_var = dict()
    for k, v in ordered_dict:
        key_var[k] = load_elem(v)
    return key_var


def to_dict_w_opt(model, metrics=None):
    """Serializes a sklearn model. Saves the parameters,
        not the attributes.

    Args:
        model(sklearn.BaseEstimator): the model to serialize,
            must be in SUPPORTED
        metrics(list, optionnal): a list of metrics to monitor

    Returns:
        a dictionnary of the serialized model
    """

    model.inputs = normalize_ordered_dict(model.inputs)
    model.outputs = normalize_ordered_dict(model.outputs)
    model.streams = normalize_ordered_dict(model.streams)

    config = dict()
    config['config'] = {'inputs': dump_dict(model.inputs),
                        'outputs': dump_dict(model.outputs),
                        'streams': dump_dict(model.streams)}

    if hasattr(model, 'hyperparameters'):
        config['hyperparameters'] = model.hyperparameters

    return config


def model_from_dict_w_opt(model_dict):
    """Builds a sklearn model from a serialized model using `to_dict_w_opt`

    Args:
        model_dict(dict): a serialized sklearn model
        custom_objects(dict, optionnal): a dictionnary mapping custom objects
            names to custom objects (callables, etc.)

    Returns:
        A new sklearn.BaseEstimator (in SUPPORTED) instance. The attributes
        are not loaded.

    """
    model = dict()

    if hasattr(model_dict['config'], 'inputs'):
        model['inputs'] = load_dict(model_dict['config']['inputs'])

    if hasattr(model_dict['config'], 'outputs'):
        model['inputs'] = load_dict(model_dict['config']['outputs'])

    if hasattr(model_dict['config'], 'streams'):
        model['inputs'] = load_dict(model_dict['config']['streams'])

    return model

