# This code is part of Qiskit.
#
# (C) Copyright IBM 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Provider for a single IBM Quantum account."""

import logging
from typing import Dict, List, Optional, Any, Callable, Union
from collections import OrderedDict
import traceback
import copy
import os

from qiskit.providers import ProviderV1 as Provider  # type: ignore[attr-defined]
from qiskit.providers.models import (QasmBackendConfiguration,
                                     PulseBackendConfiguration)
from qiskit.circuit import QuantumCircuit
from qiskit.providers.backend import BackendV1 as Backend
from qiskit.providers.basebackend import BaseBackend
from qiskit.transpiler import Layout

from qiskit_ibm.runtime import runtime_job  # pylint: disable=unused-import
from qiskit_ibm import ibm_account  # pylint: disable=unused-import,cyclic-import

from .api.clients import AuthClient, AccountClient, VersionClient
from .apiconstants import QISKIT_IBM_API_URL
from .ibm_backend import IBMBackend, IBMSimulator  # pylint: disable=cyclic-import
from .credentials import Credentials, discover_credentials
from .credentials.exceptions import HubGroupProjectInvalidStateError
from .ibm_backend_service import IBMBackendService  # pylint: disable=cyclic-import
from .utils.json_decoder import decode_backend_configuration
from .random.ibm_random_service import IBMRandomService  # pylint: disable=cyclic-import
from .experiment import IBMExperimentService  # pylint: disable=cyclic-import
from .runtime.ibm_runtime_service import IBMRuntimeService  # pylint: disable=cyclic-import
from .exceptions import (IBMNotAuthorizedError, IBMInputValueError, IBMAccountCredentialsNotFound,
                         IBMAccountCredentialsInvalidFormat, IBMAccountCredentialsInvalidToken,
                         IBMAccountCredentialsInvalidUrl, IBMProviderValueError)
from .runner_result import RunnerResult  # pylint: disable=cyclic-import

logger = logging.getLogger(__name__)


class IBMProvider(Provider):
    """Provider for a single IBM Quantum account.

    This class provides access to the IBM Quantum
    services available to this account.

    You can access the default open provider by instantiating this class
    and providing the API token.

        from qiskit_ibm import IBMProvider
        provider = IBMProvider(token=<INSERT_IBM_QUANTUM_TOKEN>)

    To access a different provider, specify the hub, group and project name of the
    desired provider during instantiation.

        from qiskit_ibm import IBMProvider
        provider = IBMProvider(token=<INSERT_IBM_QUANTUM_TOKEN>, hub='a', group='b', project='c')

    Instead of passing in the parameters during instantiation, you can also set the environment
    variables QISKIT_IBM_API_TOKEN, QISKIT_IBM_API_URL, QISKIT_IBM_HUB, QISKIT_IBM_GROUP
    and QISKIT_IBM_PROJECT and then instantiate the provider like below.

        from qiskit_ibm import IBMProvider
        provider = IBMProvider()

    If parameters are not passed and environment variables are not set then this class looks
    for credentials (token / url) and default provider (hub / group / project) stored in the
    qiskitrc file using the :meth:`IBMAccount.save_account()<IBMAccount.save_account>` method.

    `token` is the only required attribute that needs to be set using one of the above methods.
    If no `url` is set, it defaults to 'https://auth.quantum-computing.ibm.com/api'.
    If no `hub`, `group` and `project` is set, it defaults to the open provider. (ibm-q/open/main)

    You can also access a provider by enabling an account with the
    :meth:`IBMAccount.enable_account()<IBMAccount.enable_account>` method, which
    returns the default provider you have access to::

        from qiskit_ibm import IBMAccount
        account = IBMAccount()
        provider = account.enable_account(<INSERT_IBM_QUANTUM_TOKEN>)

    To select a different provider, use the
    :meth:`IBMAccount.get_provider()<IBMAccount.get_provider>` method and specify the hub,
    group, or project name of the desired provider.

    Each provider may offer different services. The main service,
    :class:`~qiskit_ibm.ibm_backend_service.IBMBackendService`, is
    available to all providers and gives access to IBM Quantum
    devices and simulators.

    You can obtain an instance of a service using the :meth:`service()` method
    or as an attribute of this ``IBMProvider`` instance. For example::

        backend_service = provider.service('backend')
        backend_service = provider.service.backend

    Since :class:`~qiskit_ibm.ibm_backend_service.IBMBackendService`
    is the main service, some of the backend-related methods are available
    through this class for convenience.

    The :meth:`backends()` method returns all the backends available to this account::

        backends = provider.backends()

    The :meth:`get_backend()` method returns a backend that matches the filters
    passed as argument. An example of retrieving a backend that matches a
    specified name::

        simulator_backend = provider.get_backend('ibmq_qasm_simulator')

    It is also possible to use the ``backend`` attribute to reference a backend.
    As an example, to retrieve the same backend from the example above::

        simulator_backend = provider.backend.ibmq_qasm_simulator

    Note:
        The ``backend`` attribute can be used to autocomplete the names of
        backends available to this provider. To autocomplete, press ``tab``
        after ``provider.backend.``. This feature may not be available
        if an error occurs during backend discovery. Also note that
        this feature is only available in interactive sessions, such as
        in Jupyter Notebook and the Python interpreter.
    """

    def __init__(
            self,
            token: Optional[str] = None,
            url: Optional[str] = None,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
            account: Optional['ibm_account.IBMAccount'] = None,
            **kwargs: Any
    ) -> None:
        """IBMProvider constructor.

        Args:
            token: IBM Quantum token.
            url: URL for the IBM Quantum authentication server.
            hub: Name of the hub to use.
            group: Name of the group to use.
            project: Name of the project to use.
            account: IBM Quantum account.
            **kwargs: Additional settings for the connection:

                * proxies (dict): proxy configuration.
                * verify (bool): verify the server's TLS certificate.

        Raises:
            IBMAccountCredentialsInvalidFormat: If the default provider stored on
                disk could not be parsed.
            IBMAccountCredentialsNotFound: If no IBM Quantum credentials
                can be found.
            IBMAccountCredentialsInvalidUrl: If the URL specified is not
                a valid IBM Quantum authentication URL.
            IBMAccountCredentialsInvalidToken: If the `token` is not a valid
                IBM Quantum token.
            IBMProviderValueError: If only one or two parameters from `hub`, `group`,
                `project` are specified.
        """
        super().__init__()

        stored_hub = None
        stored_group = None
        stored_project = None

        # This block executes when IBMProvider is instantiated directly by user
        if account is None:
            if token:
                if not isinstance(token, str):
                    raise IBMAccountCredentialsInvalidToken(
                        'Invalid IBM Quantum token '
                        'found: "{}" of type {}.'.format(token, type(token)))
                url = url or os.getenv('QISKIT_IBM_API_URL') or QISKIT_IBM_API_URL
                account_credentials = Credentials(token=token, url=url, **kwargs)
                preferences = {}  # type: Optional[Dict]
            else:
                # Check for valid credentials in env variables or qiskitrc file.
                try:
                    stored_credentials, preferences = discover_credentials()
                except HubGroupProjectInvalidStateError as ex:
                    raise IBMAccountCredentialsInvalidFormat(
                        'Invalid provider (hub/group/project) data found {}'
                        .format(str(ex))) from ex

                credentials_list = list(stored_credentials.values())

                if not credentials_list:
                    raise IBMAccountCredentialsNotFound(
                        'No IBM Quantum credentials found.')

                account_credentials = credentials_list[0]

                if account_credentials.default_provider:
                    stored_hub, stored_group, stored_project = \
                        account_credentials.default_provider.to_tuple()
                else:
                    stored_hub = account_credentials.hub
                    stored_group = account_credentials.group
                    stored_project = account_credentials.project

            version_info = self._check_api_version(account_credentials)

            # Check the URL is a valid authentication URL.
            if not version_info['new_api'] or 'api-auth' not in version_info:
                raise IBMAccountCredentialsInvalidUrl(
                    'The URL specified ({}) is not an IBM Quantum authentication URL. '
                    'Valid authentication URL: {}.'
                    .format(account_credentials.url, QISKIT_IBM_API_URL))

            auth_client = AuthClient(account_credentials.token,
                                     account_credentials.base_url,
                                     **account_credentials.connection_parameters())
            service_urls = auth_client.current_service_urls()
        else:
            # This block executes when IBMProvider is instantiated using IBMAccount
            account_credentials = account._credentials
            auth_client = account._auth_client
            service_urls = account._service_urls
            preferences = account._preferences

        # If any `hub`, `group`, or `project` is specified, make sure all are set.
        if any([hub, group, project]) and not all([hub, group, project]):
            raise IBMProviderValueError('The hub, group, and project parameters '
                                        'must all be specified. '
                                        'hub = "{}", group = "{}", project = "{}"'
                                        .format(hub, group, project))

        if not all([hub, group, project]):
            hub = stored_hub
            group = stored_group
            project = stored_project

        if not all([hub, group, project]):
            hub = 'ibm-q'
            group = 'open'
            project = 'main'

        credentials = Credentials(
            account_credentials.token,
            access_token=auth_client.current_access_token(),
            url=service_urls['http'],
            websockets_url=service_urls['ws'],
            proxies=account_credentials.proxies,
            verify=account_credentials.verify,
            services=service_urls.get('services', {}),
            default_provider=account_credentials.default_provider,
            hub=hub,
            group=group,
            project=project
        )
        credentials.preferences = \
            preferences.get(credentials.unique_id(), {})

        self.credentials = credentials
        self._account = account
        self._api_client = AccountClient(credentials,
                                         **credentials.connection_parameters())

        # Initialize the internal list of backends.
        self.__backends: Dict[str, IBMBackend] = {}
        self._backend = IBMBackendService(self)
        self.backends = self._backend.backends  # type: ignore[assignment]

        # Initialize other services.
        self._random = IBMRandomService(self) if credentials.extractor_url else None
        self._experiment = IBMExperimentService(self) if credentials.experiment_url else None
        self._runtime = IBMRuntimeService(self) \
            if credentials.runtime_url else None

        self._services = {'backend': self._backend,
                          'random': self._random,
                          'experiment': self._experiment,
                          'runtime': self._runtime}

    @property
    def _backends(self) -> Dict[str, IBMBackend]:
        """Gets the backends for the provider, if not loaded.

        Returns:
            Dict[str, IBMBackend]: the backends
        """
        if not self.__backends:
            self.__backends = self._discover_remote_backends()
        return self.__backends

    @_backends.setter
    def _backends(self, value: Dict[str, IBMBackend]) -> None:
        """Sets the value for the account's backends.

        Args:
            value: the backends
        """
        self.__backends = value

    def backends(
            self,
            name: Optional[str] = None,
            filters: Optional[Callable[[List[IBMBackend]], bool]] = None,
            **kwargs: Any
    ) -> List[IBMBackend]:
        """Return all backends accessible via this provider, subject to optional filtering.

        Args:
            name: Backend name to filter by.
            filters: More complex filters, such as lambda functions.
                For example::

                    IBMProvider.backends(filters=lambda b: b.configuration().n_qubits > 5)
            kwargs: Simple filters that specify a ``True``/``False`` criteria in the
                backend configuration, backends status, or provider credentials.
                An example to get the operational backends with 5 qubits::

                    IBMProvider.backends(n_qubits=5, operational=True)

        Returns:
            The list of available backends that match the filter.
        """
        # pylint: disable=method-hidden
        # pylint: disable=arguments-differ
        # This method is only for faking the subclassing of `BaseProvider`, as
        # `.backends()` is an abstract method. Upon initialization, it is
        # replaced by a `IBMBackendService` instance.
        pass

    def _discover_remote_backends(self, timeout: Optional[float] = None) -> Dict[str, IBMBackend]:
        """Return the remote backends available for this provider.

        Args:
            timeout: Maximum number of seconds to wait for the discovery of
                remote backends.

        Returns:
            A dict of the remote backend instances, keyed by backend name.
        """
        ret = OrderedDict()  # type: ignore[var-annotated]
        configs_list = self._api_client.list_backends(timeout=timeout)
        for raw_config in configs_list:
            # Make sure the raw_config is of proper type
            if not isinstance(raw_config, dict):
                logger.warning("An error occurred when retrieving backend "
                               "information. Some backends might not be available.")
                continue

            try:
                decode_backend_configuration(raw_config)
                try:
                    config = PulseBackendConfiguration.from_dict(raw_config)
                except (KeyError, TypeError):
                    config = QasmBackendConfiguration.from_dict(raw_config)
                backend_cls = IBMSimulator if config.simulator else IBMBackend
                ret[config.backend_name] = backend_cls(
                    configuration=config,
                    provider=self,
                    credentials=self.credentials,
                    api_client=self._api_client)
            except Exception:  # pylint: disable=broad-except
                logger.warning(
                    'Remote backend "%s" for provider %s could not be instantiated due to an '
                    'invalid config: %s',
                    raw_config.get('backend_name', raw_config.get('name', 'unknown')),
                    repr(self), traceback.format_exc())

        return ret

    def run_circuits(
            self,
            circuits: Union[QuantumCircuit, List[QuantumCircuit]],
            backend: Union[Backend, BaseBackend],
            shots: Optional[int] = None,
            initial_layout: Optional[Union[Layout, Dict, List]] = None,
            layout_method: Optional[str] = None,
            routing_method: Optional[str] = None,
            translation_method: Optional[str] = None,
            seed_transpiler: Optional[int] = None,
            optimization_level: int = 1,
            init_qubits: bool = True,
            rep_delay: Optional[float] = None,
            transpiler_options: Optional[dict] = None,
            measurement_error_mitigation: bool = False,
            use_measure_esp: Optional[bool] = None,
            **run_config: Dict
    ) -> 'runtime_job.RuntimeJob':
        """Execute the input circuit(s) on a backend using the runtime service.

        Note:
            This method uses the IBM Quantum runtime service which is not
            available to all accounts.

        Args:
            circuits: Circuit(s) to execute.

            backend: Backend to execute circuits on.
                Transpiler options are automatically grabbed from backend configuration
                and properties unless otherwise specified.

            shots: Number of repetitions of each circuit, for sampling. If not specified,
                the backend default is used.

            initial_layout: Initial position of virtual qubits on physical qubits.

            layout_method: Name of layout selection pass ('trivial', 'dense',
                'noise_adaptive', 'sabre').
                Sometimes a perfect layout can be available in which case the layout_method
                may not run.

            routing_method: Name of routing pass ('basic', 'lookahead', 'stochastic', 'sabre')

            translation_method: Name of translation pass ('unroller', 'translator', 'synthesis')

            seed_transpiler: Sets random seed for the stochastic parts of the transpiler.

            optimization_level: How much optimization to perform on the circuits.
                Higher levels generate more optimized circuits, at the expense of longer
                transpilation time.
                If None, level 1 will be chosen as default.

            init_qubits: Whether to reset the qubits to the ground state for each shot.

            rep_delay: Delay between programs in seconds. Only supported on certain
                backends (``backend.configuration().dynamic_reprate_enabled`` ). If supported,
                ``rep_delay`` will be used instead of ``rep_time`` and must be from the
                range supplied by the backend (``backend.configuration().rep_delay_range``).
                Default is given by ``backend.configuration().default_rep_delay``.

            transpiler_options: Additional transpiler options.

            measurement_error_mitigation: Whether to apply measurement error mitigation.

            use_measure_esp: Whether to use excited state promoted (ESP) readout for measurements
                which are the final instruction on a qubit. ESP readout can offer higher fidelity
                than standard measurement sequences. See
                `here <https://arxiv.org/pdf/2008.08571.pdf>`_.

            **run_config: Extra arguments used to configure the circuit execution.

        Returns:
            Runtime job.
        """
        inputs = copy.deepcopy(run_config)  # type: Dict[str, Any]
        inputs['circuits'] = circuits
        inputs['optimization_level'] = optimization_level
        inputs['init_qubits'] = init_qubits
        inputs['measurement_error_mitigation'] = measurement_error_mitigation
        if shots:
            inputs['shots'] = shots
        if initial_layout:
            inputs['initial_layout'] = initial_layout
        if layout_method:
            inputs['layout_method'] = layout_method
        if routing_method:
            inputs['routing_method'] = routing_method
        if translation_method:
            inputs['translation_method'] = translation_method
        if seed_transpiler:
            inputs['seed_transpiler'] = seed_transpiler
        if rep_delay:
            inputs['rep_delay'] = rep_delay
        if transpiler_options:
            inputs['transpiler_options'] = transpiler_options
        if use_measure_esp is not None:
            inputs['use_measure_esp'] = use_measure_esp

        options = {'backend_name': backend.name()}
        return self.runtime.run('circuit-runner', options=options, inputs=inputs,
                                result_decoder=RunnerResult)

    def service(self, name: str) -> Any:
        """Return the specified service.

        Args:
            name: Name of the service.

        Returns:
            The specified service.

        Raises:
            IBMInputValueError: If an unknown service name is specified.
            IBMNotAuthorizedError: If the account is not authorized to use
                the service.
        """
        if name not in self._services:
            raise IBMInputValueError(f"Unknown service {name} specified.")

        if self._services[name] is None:
            raise IBMNotAuthorizedError("You are not authorized to use this service.")

        return self._services[name]

    def services(self) -> Dict:
        """Return all available services.

        Returns:
            All services available to this provider.
        """
        return {key: val for key, val in self._services.items() if val is not None}

    def has_service(self, name: str) -> bool:
        """Check if this provider has access to the service.

        Args:
            name: Name of the service.

        Returns:
            Whether the provider has access to the service.

        Raises:
            IBMInputValueError: If an unknown service name is specified.
        """
        if name not in self._services:
            raise IBMInputValueError(f"Unknown service {name} specified.")

        if self._services[name] is None:
            return False

        return True

    @property
    def backend(self) -> IBMBackendService:
        """Return the backend service.

        Returns:
            The backend service instance.
        """
        return self._backend

    @property
    def experiment(self) -> IBMExperimentService:
        """Return the experiment service.

        Returns:
            The experiment service instance.

        Raises:
            IBMNotAuthorizedError: If the account is not authorized to use
                the experiment service.
        """
        if self._experiment:
            return self._experiment
        else:
            raise IBMNotAuthorizedError("You are not authorized to use the experiment service.")

    @property
    def random(self) -> IBMRandomService:
        """Return the random number service.

        Returns:
            The random number service instance.

        Raises:
            IBMNotAuthorizedError: If the account is not authorized to use
                the service.
        """
        if self._random:
            return self._random
        else:
            raise IBMNotAuthorizedError("You are not authorized to use the service.")

    @property
    def runtime(self) -> IBMRuntimeService:
        """Return the runtime service.

        Returns:
            The runtime service instance.

        Raises:
            IBMNotAuthorizedError: If the account is not authorized to use the service.
        """
        if self._runtime:
            return self._runtime
        else:
            raise IBMNotAuthorizedError("You are not authorized to use the runtime service.")

    def __eq__(
            self,
            other: Any
    ) -> bool:
        if not isinstance(other, IBMProvider):
            return False
        return self.credentials == other.credentials

    def __repr__(self) -> str:
        credentials_info = "hub='{}', group='{}', project='{}'".format(
            self.credentials.hub, self.credentials.group, self.credentials.project)

        return "<{} for IBMAccount({})>".format(
            self.__class__.__name__, credentials_info)

    @staticmethod
    def _check_api_version(credentials: Credentials) -> Dict[str, Union[bool, str]]:
        """Check the version of the remote server in a set of credentials.

        Returns:
            A dictionary with version information.
        """
        version_finder = VersionClient(credentials.base_url,
                                       **credentials.connection_parameters())
        return version_finder.version()
