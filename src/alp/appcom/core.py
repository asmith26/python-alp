"""
.. codeauthor:: Thomas Boquet thomas.boquet@r2.ca

A simple module to perform training and prediction of models
------------------------------------------------------------------

Using `celery <http://www.celeryproject.org/>`_, this module helps to schedule
the training of models if the users send enough models in a short
period of time.

"""

import copy
import sys

from ..appcom.utils import background
from ..backend import common as cm
from ..dbbackend import get_models
from .utils import init_backend
from .utils import switch_backend
from .utils import transform_gen


class Experiment(object):
    """An Experiment trains, predicts, saves and logs a model

    Attributes:
        model(model): the model used in the experiment
        metrics(list): a list of callables
    """

    def __init__(self, model, metrics=None):
        backend, backend_name, backend_version = init_backend(model)
        self.backend = backend
        self.backend_name = backend_name
        self.backend_version = backend_version
        self.metrics = metrics
        self.model = model
        self.model_dict = self.backend.to_dict_w_opt(self.model,
                                                     self.metrics)
        self.trained = False

    @property
    def model_dict(self):
        return self.__model_dict

    @model_dict.setter
    def model_dict(self, model_dict):
        if isinstance(model_dict, dict) or model_dict is None:
            self.__model_dict = dict()
            self.__model_dict['model_arch'] = model_dict
            self.__model_dict['mod_id'] = None
            self.__model_dict['params_dump'] = None
            self.__model_dict['data_id'] = None
        else:
            self.model = model_dict
            backend, backend_name, backend_version = init_backend(model_dict)
            self.backend = backend
            self.backend_name = backend_name
            self.backend_version = backend_version
            self.__model_dict['model_arch'] = self.backend.to_dict_w_opt(
                self.model, self.metrics)
            self.__model_dict['mod_id'] = None
            self.__model_dict['data_id'] = None
            self.__model_dict['params_dump'] = None

    @property
    def params_dump(self):
        return self.__params_dump

    @params_dump.setter
    def params_dump(self, params_dump):
        self.__model_dict['params_dump'] = params_dump
        self.__params_dump = params_dump

    @property
    def mod_id(self):
        return self.__mod_id

    @mod_id.setter
    def mod_id(self, mod_id):
        self.__model_dict['mod_id'] = mod_id
        self.__mod_id = mod_id

    @property
    def data_id(self):
        return self.__data_id

    @data_id.setter
    def data_id(self, data_id):
        self.__model_dict['data_id'] = data_id
        self.__data_id = data_id

    def fit(self, data, data_val, model=None, *args, **kwargs):
        """Build and fit a model given data and hyperparameters

        Args:
            data(list(dict)): a list of dictionnaries mapping inputs and
                outputs names to numpy arrays for training.
            data_val(list(dict)): a list of dictionnaries mapping inputs and
                outputs names to numpy arrays for validation.
            model(model, optionnal): a model from a supported backend

        Returns:
            the id of the model in the db, the id of the data in the db and
            path to the parameters.
        """
        res = self._prepare_fit(model, data, data_val, False, False,
                                *args, **kwargs)
        return res

    def fit_async(self, data, data_val, model=None,
                  *args, **kwargs):
        """Build and fit asynchronously a model given data and hyperparameters

        Args:
            data(list(dict)): a list of dictionnaries mapping inputs and
                outputs names to numpy arrays for training.
            data_val(list(dict)): a list of dictionnaries mapping inputs and
                outputs names to numpy arrays for validation.
            model(model, optionnal): a model from a supported backend

        Returns:
            the id of the model in the db, the id of the data in the db and a
            path to the parameters.
        """
        res = self._prepare_fit(model, data, data_val, False, True,
                                *args, **kwargs)

        return res

    def fit_gen(self, gen_train, data_val,
                model=None, *args, **kwargs):
        """Build and fit asynchronously a model given data and hyperparameters

        Args:
            gen_train(list(dict)): a list of generators.
            data_val(list(dict)): a list of dictionnaries mapping inputs and
                outputs names to numpy arrays or generators for validation.
            model(model, optionnal): a model from a supported backend

        Returns:
            the id of the model in the db, the id of the data in the db and a
            path to the parameters.
        """
        res = self._prepare_fit(model, gen_train, data_val, True, False,
                                *args, **kwargs)

        return res

    def fit_gen_async(self, gen_train, data_val,
                      model=None, *args, **kwargs):
        """Build and fit asynchronously a model given generator(s) and
        hyperparameters.

        Args:
            gen_train(list(dict)): a list of generators.
            data_val(list(dict)): a list of dictionnaries mapping inputs and
                outputs names to numpy arrays or generators for validation.
            model(model, optionnal): a model from a supported backend

        Returns:
            the id of the model in the db, the id of the data in the db and a
            path to the parameters.
        """
        res = self._prepare_fit(model, gen_train, data_val, True, True,
                                *args, **kwargs)
        return res

    def load_model(self, mod_id=None, data_id=None):
        """Load a model from the database form it's mod_id and data_id

        Args:
            mod_id(str): the id of the model in the database
            data_id(str): the id of the data in the database"""
        if mod_id is None and data_id is None:
            mod_id = self.mod_id
            data_id = self.data_id
        assert mod_id is not None, 'You must provide a model id'
        assert data_id is not None, 'You must provide a data id'
        models = get_models()
        model_db = models.find_one({'mod_id': mod_id, 'data_id': data_id})
        self._switch_backend(model_db)
        self.model_dict = model_db['model_arch']
        self.params_dump = model_db['params_dump']
        self.mod_id = model_db['mod_id']
        self.data_id = model_db['data_id']
        self.trained = True

    def predict(self, data):
        """Make predictions given data

        Args:
            data(np.array):

        Returns:
            an np.array of predictions"""
        if self.trained:
            return self.backend.predict(self.model_dict, data)
        else:
            raise Exception("You must have a trained model"
                            "in order to make predictions")

    def _check_compile(self, model, kwargs_m):
        """Check if we have to recompile and reserialize the model

        Args:
            model(a supported model): the model sent (could be None).
            kwargs_m(dict): the keyword arguments passed to the wrapper
        """
        _recompile = False
        if model is not None:
            self.model = model
            _recompile = True
        if "metrics" in kwargs_m:
            self.metrics = kwargs_m.pop("metrics")
            _recompile = True

        if _recompile is True:
            self.model_dict = self.backend.to_dict_w_opt(self.model,
                                                         self.metrics)

        if self.model is None:
            raise Exception('No model provided')

    def _switch_backend(self, model_db):
        """A utility function to switch backend when loading a model

        Args:
            model_db(dict): the dictionnary stored in the database
        """
        if model_db['backend_name'] != self.backend_name:
            backend = switch_backend(model_db['backend_name'])
            self.backend_name = backend.__name__
            self.backend_version = None
            if hasattr(backend, '__version__'):
                check = self.backend_version != backend.__version__
                self.backend_version = backend.__version__
            if check:  # pragma: no cover
                sys.stderr.write('Warning: the backend versions'
                                 'do not match.\n')  # pragma: no cover

    def _check_serialize(self, kwargs):
        """Serialize the object mapped in the kwargs

        Args:
           kwargs(dict): keyword arguments

        Returns:
            kwargs
        """
        for k in kwargs:
            if k in self.backend.TO_SERIALIZE:
                kwargs[k] = {j: self.backend.serialize(kwargs[k][j])
                             for j in kwargs[k]}
        return kwargs

    def _prepare_message(self, model, data, data_val, kwargs, generator=False):
        """Prepare the elements to be passed to the backend

        Args:
            model(supported model): the model to be prepared
            data(list): the list of dicts or generators used for training
            data_val(list): the list of dicts or generator used for validation

        Returns:
           the transformed data object, the transformed validation data object,
           the data_hash
        """
        self._check_compile(model, kwargs)

        kwargs = self._check_serialize(kwargs)

        if generator:
            data_hash = cm.create_gen_hash(data)
            data, data_val = transform_gen(data, data_val)
        else:
            data_hash = cm.create_data_hash(data)

        return data, data_val, data_hash

    def _prepare_fit(self, model, data, data_val,
                     generator=False, delay=False,
                     *args, **kwargs):
        """Prepare the model and the datasets and fit the model

        Args:
            model(a supported model): the model to send
            data(dict or generator): the training data
            data_val(dict or generator): the validation data
            generator(bool): if True, transforms the generators
            delay(bool): if True, fits the model in asynchronous mode
            """
        data, data_val, data_hash = self._prepare_message(model,
                                                          data,
                                                          data_val,
                                                          kwargs,
                                                          generator)

        f = self.backend.fit
        if delay:
            f = self.backend.fit.delay
        res = f(self.backend_name,
                self.backend_version,
                copy.deepcopy(self.model_dict),
                data, data_hash, data_val,
                generator=generator,
                *args, **kwargs)
        return self._handle_results(res, delay)

    def _handle_results(self, res, delay):
        """Modify the Experiment given the results received from the worker

        Args:
            res(celery result or dict): the results returned by the model
            delay(bool): if True the result is an async celery result

        Returns:
            the results and the thread used to handle the results"""
        if delay:
            thread = self._get_results(res)
        else:
            self.mod_id = res['model_id']
            self.data_id = res['data_id']
            self.params_dump = res['params_dump']

            self.trained = True
            self.full_res = res
            thread = None
        return res, thread

    @background
    def _get_results(self, res):
        """Handle the results of an asynchronous task

        Args:
            res(async result): result of an asynchronous task"""
        self.async_res = res
        self.full_res = res.wait()  # pragma: no cover
        self.trained = True  # pragma: no cover
        self.mod_id = self.full_res['model_id']  # pragma: no cover
        self.data_id = self.full_res['data_id']  # pragma: no cover
        self.params_dump = self.full_res['params_dump']  # pragma: no cover
        print("Result {} ready".format(self.mod_id))  # pragma: no cover
