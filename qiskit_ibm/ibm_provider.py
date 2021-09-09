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
from typing import Dict, List, Optional, Any, Callable, Tuple, Union
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

from .api.clients import AuthClient, AccountClient, VersionClient
from .apiconstants import QISKIT_IBM_API_URL
from .ibm_backend import IBMBackend, IBMSimulator  # pylint: disable=cyclic-import
from .credentials import Credentials, HubGroupProject, discover_credentials
from .credentials.configrc import (remove_credentials, read_credentials_from_qiskitrc,
                                   store_credentials)
from .credentials.exceptions import HubGroupProjectInvalidStateError
from .ibm_backend_service import IBMBackendService  # pylint: disable=cyclic-import
from .utils.json_decoder import decode_backend_configuration
from .random.ibm_random_service import IBMRandomService  # pylint: disable=cyclic-import
from .experiment import IBMExperimentService  # pylint: disable=cyclic-import
from .runtime.ibm_runtime_service import IBMRuntimeService  # pylint: disable=cyclic-import
from .exceptions import (IBMNotAuthorizedError, IBMInputValueError, IBMProviderCredentialsNotFound,
                         IBMProviderCredentialsInvalidFormat, IBMProviderCredentialsInvalidToken,
                         IBMProviderCredentialsInvalidUrl, IBMProviderError, IBMProviderValueError)
from .runner_result import RunnerResult  # pylint: disable=cyclic-import

logger = logging.getLogger(__name__)


class IBMProvider(Provider):
    """Provider for a single IBM Quantum account.

    This class provides access to the IBM Quantum services available to an account.

    You can access the default open provider by instantiating this class
    and providing the API token.

        from qiskit_ibm import IBMProvider
        provider = IBMProvider(token=<INSERT_IBM_QUANTUM_TOKEN>)

    To access a different provider, specify the hub, group and project name of the
    desired provider during instantiation.

        from qiskit_ibm import IBMProvider
        provider = IBMProvider(token=<INSERT_IBM_QUANTUM_TOKEN>, hub='ibm-q', group='test',
                               project='default')

    Instead of passing in the parameters during instantiation, you can also set the environment
    variables QISKIT_IBM_API_TOKEN, QISKIT_IBM_API_URL, QISKIT_IBM_HUB, QISKIT_IBM_GROUP
    and QISKIT_IBM_PROJECT and then instantiate the provider like below.

        from qiskit_ibm import IBMProvider
        provider = IBMProvider()

    If parameters are not passed and environment variables are not set then this class looks
    for credentials (token / url) and default provider (hub / group / project) saved in the
    qiskitrc file. Credentials can be saved by calling the `save_account()` method.

        from qiskit_ibm import IBMProvider
        IBMProvider.save_account(token=<INSERT_IBM_QUANTUM_TOKEN>, hub='ibm-q', group='open',
                               project='main')

    `token` is the only required attribute that needs to be set using one of the above methods.
    If no `url` is set, it defaults to 'https://auth.quantum-computing.ibm.com/api'.
    If no `hub`, `group` and `project` is set, it defaults to the open provider. (ibm-q/open/main)

    Once credentails are saved you can simply instantiate the provider like below to load the
    saved account.

    from qiskit_ibm import IBMProvider
    provider = IBMProvider()

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

    _providers = OrderedDict()  # type: Dict[HubGroupProject, IBMProvider]

    def __new__(
            cls,
            token: Optional[str] = None,
            url: Optional[str] = None,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
            account: Optional[Dict] = None,
            **kwargs: Any
    ) -> 'IBMProvider':
        account_credentials, account_preferences, hub, group, project = cls._resolve_credentials(
            token=token,
            url=url,
            hub=hub,
            group=group,
            project=project,
            **kwargs
        )

        if not account and (not cls._providers or
                            cls._is_different_account(account_credentials.token)):
            if cls._providers:
                logger.warning('Credentials are already in use. The existing '
                               'account in the session will be replaced.')
                cls.disable_account()
            cls._initialize_providers(credentials=account_credentials,
                                      preferences=account_preferences)
            instance = cls._get_provider(hub=hub, group=group, project=project)
            return instance
        elif not account and cls._providers:
            instance = cls._get_provider(hub=hub, group=group, project=project)
            return instance
        else:
            instance = object.__new__(cls)
            return instance

    @classmethod
    def _is_different_account(cls, token: str) -> bool:
        first_provider = list(cls._providers.values())[0]
        return token != first_provider.credentials.token

    def __init__(
            self,
            token: Optional[str] = None,
            url: Optional[str] = None,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
            account: Optional[Dict] = None,
            **kwargs: Any
    ) -> None:
        """IBMProvider constructor.

        Args:
            token: IBM Quantum token.
            url: URL for the IBM Quantum authentication server.
            hub: Name of the hub to use.
            group: Name of the group to use.
            project: Name of the project to use.
            account: Dictionary containing account credentials
            **kwargs: Additional settings for the connection:

                * proxies (dict): proxy configuration.
                * verify (bool): verify the server's TLS certificate.

        Raises:
            IBMProviderCredentialsInvalidFormat: If the default provider stored on
                disk could not be parsed.
            IBMProviderCredentialsNotFound: If no IBM Quantum credentials
                can be found.
            IBMProviderCredentialsInvalidUrl: If the URL specified is not
                a valid IBM Quantum authentication URL.
            IBMProviderCredentialsInvalidToken: If the `token` is not a valid
                IBM Quantum token.
            IBMProviderValueError: If only one or two parameters from `hub`, `group`,
                `project` are specified.
        """
        # pylint: disable=unused-argument
        super().__init__()

        if account:
            self.credentials = self._construct_provider_credentials(
                account['credentials'],
                account['preferences'],
                account['auth_client'],
                account['service_urls'],
                hub,
                group,
                project
            )
            self._api_client = AccountClient(self.credentials,
                                             **self.credentials.connection_parameters())

            # Initialize the internal list of backends.
            self.__backends: Dict[str, IBMBackend] = {}
            self._backend = IBMBackendService(self)
            self.backends = self._backend.backends  # type: ignore[assignment]

            # Initialize other services.
            self._random = IBMRandomService(self) if self.credentials.extractor_url else None
            self._experiment = IBMExperimentService(self) \
                if self.credentials.experiment_url else None
            self._runtime = IBMRuntimeService(self) \
                if self.credentials.runtime_url else None

            self._services = {'backend': self._backend,
                              'random': self._random,
                              'experiment': self._experiment,
                              'runtime': self._runtime}

    @classmethod
    def _initialize_providers(
            cls,
            credentials: Credentials,
            preferences: Optional[Dict] = None
    ) -> None:
        """Authenticate against IBM Quantum and populate the providers.

        Args:
            credentials: Credentials for IBM Quantum.
            preferences: Account preferences.
        """
        account = dict()  # type: Dict[str, Any]
        account['auth_client'] = AuthClient(credentials.token,
                                            credentials.base_url,
                                            **credentials.connection_parameters())
        account['service_urls'] = account['auth_client'].current_service_urls()
        account['user_hubs'] = account['auth_client'].user_hubs()
        account['preferences'] = preferences or {}
        account['credentials'] = credentials

        for hub_info in account['user_hubs']:
            # Build the provider.
            try:
                provider = IBMProvider(token=credentials.token, **hub_info, account=account)
                cls._providers[provider.credentials.unique_id()] = provider
            except Exception:  # pylint: disable=broad-except
                # Catch-all for errors instantiating the provider.
                logger.warning('Unable to instantiate provider for %s: %s',
                               hub_info, traceback.format_exc())

    @classmethod
    def _resolve_credentials(
            cls,
            token: Optional[str] = None,
            url: Optional[str] = None,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
            **kwargs: Any
    ) -> Tuple[Credentials, Dict, str, str, str]:

        saved_hub = None
        saved_group = None
        saved_project = None

        if token:
            if not isinstance(token, str):
                raise IBMProviderCredentialsInvalidToken(
                    'Invalid IBM Quantum token '
                    'found: "{}" of type {}.'.format(token, type(token)))
            url = url or os.getenv('QISKIT_IBM_API_URL') or QISKIT_IBM_API_URL
            account_credentials = Credentials(token=token, url=url, api_url=url, **kwargs)
            preferences = {}  # type: Optional[Dict]
        else:
            # Check for valid credentials in env variables or qiskitrc file.
            try:
                saved_credentials, preferences = discover_credentials()
            except HubGroupProjectInvalidStateError as ex:
                raise IBMProviderCredentialsInvalidFormat(
                    'Invalid provider (hub/group/project) data found {}'
                    .format(str(ex))) from ex

            credentials_list = list(saved_credentials.values())

            if not credentials_list:
                raise IBMProviderCredentialsNotFound(
                    'No IBM Quantum credentials found.')

            account_credentials = credentials_list[0]

            if account_credentials.default_provider:
                saved_hub, saved_group, saved_project = \
                    account_credentials.default_provider.to_tuple()
            else:
                saved_hub = account_credentials.hub
                saved_group = account_credentials.group
                saved_project = account_credentials.project

        version_info = cls._check_api_version(account_credentials)

        # Check the URL is a valid authentication URL.
        if not version_info['new_api'] or 'api-auth' not in version_info:
            raise IBMProviderCredentialsInvalidUrl(
                'The URL specified ({}) is not an IBM Quantum authentication URL. '
                'Valid authentication URL: {}.'
                .format(account_credentials.url, QISKIT_IBM_API_URL))

        hub, group, project = cls._resolve_hub_group_project(
            hub=hub, group=group, project=project, saved_hub=saved_hub, saved_group=saved_group,
            saved_project=saved_project, url=account_credentials.url
        )

        return account_credentials, preferences, hub, group, project

    @classmethod
    def _resolve_hub_group_project(
            cls,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
            saved_hub: Optional[str] = None,
            saved_group: Optional[str] = None,
            saved_project: Optional[str] = None,
            url: Optional[str] = None
    ) -> Tuple[str, str, str]:
        # If any `hub`, `group`, or `project` is specified, make sure all are set.
        if any([hub, group, project]):
            return hub, group, project

        if any([saved_hub, saved_group, saved_project]):
            return saved_hub, saved_group, saved_project

        if url == QISKIT_IBM_API_URL:
            hub = 'ibm-q'
            group = 'open'
            project = 'main'

        return hub, group, project

    @classmethod
    def _get_provider(
            cls,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
    ) -> 'IBMProvider':
        providers = cls.providers(hub, group, project)
        if not providers:
            raise IBMProviderError('No provider matches the specified criteria: '
                                   'hub = {}, group = {}, project = {}'
                                   .format(hub, group, project))
        if len(providers) > 1:
            raise IBMProviderError('More than one provider matches the specified criteria.'
                                   'hub = {}, group = {}, project = {}'
                                   .format(hub, group, project))
        return providers[0]

    def _construct_provider_credentials(
            self,
            account_credentials: Credentials,
            preferences: Optional[Dict],
            auth_client: AuthClient,
            service_urls: Dict[str, str],
            hub: str,
            group: str,
            project: str
    ) -> Credentials:
        credentials = Credentials(
            account_credentials.token,
            access_token=auth_client.current_access_token(),
            url=service_urls['http'],
            api_url=account_credentials.api_url,
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
        return credentials

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

        return "<{}({})>".format(
            self.__class__.__name__, credentials_info)

    @classmethod
    def disable_account(cls) -> None:
        """Disable the account currently in use for the session.

        Raises:
            IBMProviderCredentialsNotFound: If no account is in use for the session.
        """
        if not cls._providers:
            raise IBMProviderCredentialsNotFound(
                'No IBM Quantum account is in use for the session.')
        cls._providers = OrderedDict()

    @classmethod
    def active_account(cls) -> Optional[Dict[str, str]]:
        """Return the IBM Quantum account currently in use for the session.

        Returns:
            Information about the account currently in the session.
        """
        if not cls._providers:
            return None
        first_provider = list(cls._providers.values())[0]
        return {
            'token': first_provider.credentials.token,
            'url': first_provider.credentials.api_url
        }

    @classmethod
    def providers(
            cls,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None
    ) -> List['IBMProvider']:
        """Return a list of providers, subject to optional filtering.

        Args:
            hub: Name of the hub.
            group: Name of the group.
            project: Name of the project.

        Returns:
            A list of providers that match the specified criteria.
        """
        filters = []  # type: List[Callable[[HubGroupProject], bool]]

        if hub:
            filters.append(lambda hgp: hgp.hub == hub)
        if group:
            filters.append(lambda hgp: hgp.group == group)
        if project:
            filters.append(lambda hgp: hgp.project == project)

        providers = [provider for key, provider in cls._providers.items()
                     if all(f(key) for f in filters)]

        return providers

    @staticmethod
    def save_account(
            token: str,
            url: str = QISKIT_IBM_API_URL,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
            overwrite: bool = False,
            **kwargs: Any
    ) -> None:
        """Save the account to disk for future use.

        Note:
            If storing a default provider to disk, all three parameters
            `hub`, `group`, `project` must be specified.

        Args:
            token: IBM Quantum token.
            url: URL for the IBM Quantum authentication server.
            hub: Name of the hub for the default provider to store on disk.
            group: Name of the group for the default provider to store on disk.
            project: Name of the project for the default provider to store on disk.
            overwrite: Overwrite existing credentials.
            **kwargs:
                * proxies (dict): Proxy configuration for the server.
                * verify (bool): If False, ignores SSL certificates errors

        Raises:
            IBMProviderCredentialsInvalidUrl: If the `url` is not a valid
                IBM Quantum authentication URL.
            IBMProviderCredentialsInvalidToken: If the `token` is not a valid
                IBM Quantum token.
            IBMProviderValueError: If only one or two parameters from `hub`, `group`,
                `project` are specified.
        """
        if url != QISKIT_IBM_API_URL:
            raise IBMProviderCredentialsInvalidUrl(
                'Invalid IBM Quantum credentials found.')

        if not token or not isinstance(token, str):
            raise IBMProviderCredentialsInvalidToken(
                'Invalid IBM Quantum token '
                'found: "{}" of type {}.'.format(token, type(token)))

        # If any `hub`, `group`, or `project` is specified, make sure all parameters are set.
        if any([hub, group, project]) and not all([hub, group, project]):
            raise IBMProviderValueError('The hub, group, and project parameters must all be '
                                        'specified when storing a default provider to disk: '
                                        'hub = "{}", group = "{}", project = "{}"'
                                        .format(hub, group, project))

        # If specified, get the provider to store.
        default_provider_hgp = HubGroupProject(hub, group, project) \
            if all([hub, group, project]) else None

        credentials = Credentials(token=token, url=url,
                                  default_provider=default_provider_hgp, **kwargs)

        store_credentials(credentials,
                          overwrite=overwrite)

    @staticmethod
    def delete_account() -> None:
        """Delete the saved account from disk.

        Raises:
            IBMProviderCredentialsNotFound: If no valid IBM Quantum
                credentials can be found on disk.
            IBMProviderCredentialsInvalidUrl: If invalid IBM Quantum
                credentials are found on disk.
        """
        stored_credentials, _ = read_credentials_from_qiskitrc()
        if not stored_credentials:
            raise IBMProviderCredentialsNotFound(
                'No IBM Quantum credentials found on disk.')

        credentials = list(stored_credentials.values())[0]

        if credentials.url != QISKIT_IBM_API_URL:
            raise IBMProviderCredentialsInvalidUrl(
                'Invalid IBM Quantum credentials found on disk. ')

        remove_credentials(credentials)

    @staticmethod
    def saved_account() -> Dict[str, str]:
        """List the account saved on disk.

        Returns:
            A dictionary with information about the account stored on disk.

        Raises:
            IBMProviderCredentialsInvalidUrl: If invalid IBM Quantum
                credentials are found on disk.
        """
        stored_credentials, _ = read_credentials_from_qiskitrc()
        if not stored_credentials:
            return {}

        credentials = list(stored_credentials.values())[0]

        if credentials.url != QISKIT_IBM_API_URL:
            raise IBMProviderCredentialsInvalidUrl(
                'Invalid IBM Quantum credentials found on disk.')

        return {
            'token': credentials.token,
            'url': credentials.url
        }

    @staticmethod
    def _check_api_version(credentials: Credentials) -> Dict[str, Union[bool, str]]:
        """Check the version of the remote server in a set of credentials.

        Returns:
            A dictionary with version information.
        """
        version_finder = VersionClient(credentials.base_url,
                                       **credentials.connection_parameters())
        return version_finder.version()
