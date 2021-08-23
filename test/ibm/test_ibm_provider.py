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

"""Tests for the IBMProvider class."""

from datetime import datetime

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.test import providers, slow_test
from qiskit.compiler import transpile
from qiskit.providers.exceptions import QiskitBackendNotFoundError
from qiskit.providers.models.backendproperties import BackendProperties
from qiskit_ibm import IBMAccount
from qiskit_ibm.ibm_provider import IBMProvider
from qiskit_ibm.ibm_backend import IBMSimulator, IBMBackend
from qiskit_ibm.ibm_backend_service import IBMBackendService
from qiskit_ibm.experiment import IBMExperimentService
from qiskit_ibm.exceptions import (IBMProviderValueError, IBMAccountCredentialsInvalidUrl,
                                   IBMAccountCredentialsNotFound)
from qiskit_ibm.random.ibm_random_service import IBMRandomService

from ..decorators import requires_provider, requires_device, requires_qe_access
from ..ibm_test_case import IBMTestCase
from ..contextmanagers import custom_qiskitrc, no_envs, CREDENTIAL_ENV_VARS

API_URL = 'https://api.quantum-computing.ibm.com/api'


class TestIBMProviderInitialization(IBMTestCase):
    """Tests for the IBMProvider class initialization."""

    def setUp(self):
        """Initial test setup."""
        super().setUp()
        self.account = IBMAccount()

    @requires_qe_access
    def test_provider_init_token(self, qe_token, qe_url):
        """Test initializing a provider with only API token."""
        # pylint: disable=unused-argument
        provider = IBMProvider(token=qe_token)
        self.assertIsInstance(provider, IBMProvider)
        self.assertEqual(provider.credentials.token, qe_token)
        self.assertEqual(provider.credentials.hub, 'ibm-q')
        self.assertEqual(provider.credentials.group, 'open')
        self.assertEqual(provider.credentials.project, 'main')

    @requires_qe_access
    def test_provider_init_token_url(self, qe_token, qe_url):
        """Test initializing a provider with API token and URL."""
        provider = IBMProvider(token=qe_token, url=qe_url)
        self.assertIsInstance(provider, IBMProvider)
        self.assertEqual(provider.credentials.token, qe_token)
        self.assertEqual(provider.credentials.hub, 'ibm-q')
        self.assertEqual(provider.credentials.group, 'open')
        self.assertEqual(provider.credentials.project, 'main')

    @requires_qe_access
    def test_provider_init_token_url_hgp(self, qe_token, qe_url):
        """Test initializing a provider with API token, URL and Hub/Group/Project."""
        provider = IBMProvider(
            token=qe_token, url=qe_url, hub='ibm-q', group='open', project='main')
        self.assertIsInstance(provider, IBMProvider)
        self.assertEqual(provider.credentials.token, qe_token)
        self.assertEqual(provider.credentials.hub, 'ibm-q')
        self.assertEqual(provider.credentials.group, 'open')
        self.assertEqual(provider.credentials.project, 'main')

    @requires_qe_access
    def test_provider_init_token_url_hub(self, qe_token, qe_url):
        """Test initializing a provider with API token, URL and Hub."""

        with self.assertRaises(IBMProviderValueError) as context_manager:
            IBMProvider(token=qe_token, url=qe_url, hub='ibm-q')

        self.assertIn('The hub, group, and project parameters must all be specified.',
                      str(context_manager.exception))

    @requires_qe_access
    def test_provider_init_token_url_group(self, qe_token, qe_url):
        """Test initializing a provider with API token, URL and Group."""

        with self.assertRaises(IBMProviderValueError) as context_manager:
            IBMProvider(token=qe_token, url=qe_url, group='open')

        self.assertIn('The hub, group, and project parameters must all be specified.',
                      str(context_manager.exception))

    @requires_qe_access
    def test_provider_init_token_url_project(self, qe_token, qe_url):
        """Test initializing a provider with API token, URL and Project."""

        with self.assertRaises(IBMProviderValueError) as context_manager:
            IBMProvider(token=qe_token, url=qe_url, project='main')

        self.assertIn('The hub, group, and project parameters must all be specified.',
                      str(context_manager.exception))

    @requires_qe_access
    def test_provider_init_saved_account(self, qe_token, qe_url):
        """Test initializing a provider with credentials from qiskitrc file."""
        with custom_qiskitrc(), no_envs(CREDENTIAL_ENV_VARS):
            self.account.save(qe_token, url=qe_url)
            provider = IBMProvider()

        self.assertIsInstance(provider, IBMProvider)
        self.assertEqual(provider.credentials.token, qe_token)
        self.assertEqual(provider.credentials.hub, 'ibm-q')
        self.assertEqual(provider.credentials.group, 'open')
        self.assertEqual(provider.credentials.project, 'main')

    def test_provider_init_non_auth_url(self):
        """Test initializing provider with a non-auth URL."""
        qe_token = 'invalid'
        qe_url = API_URL

        with self.assertRaises(IBMAccountCredentialsInvalidUrl) as context_manager:
            IBMProvider(token=qe_token, url=qe_url)

        self.assertIn('authentication URL', str(context_manager.exception))

    def test_provider_init_non_auth_url_with_hub(self):
        """Test initializing provider with a non-auth URL containing h/g/p."""
        qe_token = 'invalid'
        qe_url = API_URL + '/Hubs/X/Groups/Y/Projects/Z'

        with self.assertRaises(IBMAccountCredentialsInvalidUrl) as context_manager:
            IBMProvider(token=qe_token, url=qe_url)

        self.assertIn('authentication URL', str(context_manager.exception))

    def test_provider_init_no_credentials(self):
        """Test initializing provider with no credentials."""
        with self.assertRaises(IBMAccountCredentialsNotFound) as context_manager, \
             no_envs(CREDENTIAL_ENV_VARS):
            IBMProvider()

        self.assertIn('No IBM Quantum credentials found.', str(context_manager.exception))


class TestIBMProvider(IBMTestCase, providers.ProviderTestCase):
    """Tests for the IBMProvider class."""

    provider_cls = IBMProvider
    backend_name = 'ibmq_qasm_simulator'

    def setUp(self):
        """Initial test setup."""
        super().setUp()
        qr = QuantumRegister(1)
        cr = ClassicalRegister(1)
        self.qc1 = QuantumCircuit(qr, cr, name='circuit0')
        self.qc1.h(qr[0])
        self.qc1.measure(qr, cr)

    @requires_provider
    def _get_provider(self, provider):
        """Return an instance of a provider."""
        # pylint: disable=arguments-differ
        return provider

    def test_remote_backends_exist_real_device(self):
        """Test if there are remote backends that are devices."""
        remotes = self.provider.backends(simulator=False)
        self.assertTrue(remotes)

    def test_remote_backends_exist_simulator(self):
        """Test if there are remote backends that are simulators."""
        remotes = self.provider.backends(simulator=True)
        self.assertTrue(remotes)

    def test_remote_backends_instantiate_simulators(self):
        """Test if remote backends that are simulators are an ``IBMSimulator`` instance."""
        remotes = self.provider.backends(simulator=True)
        for backend in remotes:
            with self.subTest(backend=backend):
                self.assertIsInstance(backend, IBMSimulator)

    def test_remote_backend_status(self):
        """Test backend_status."""
        remotes = self.provider.backends()
        for backend in remotes:
            _ = backend.status()

    def test_remote_backend_configuration(self):
        """Test backend configuration."""
        remotes = self.provider.backends()
        for backend in remotes:
            _ = backend.configuration()

    def test_remote_backend_properties(self):
        """Test backend properties."""
        remotes = self.provider.backends(simulator=False)
        for backend in remotes:
            properties = backend.properties()
            if backend.configuration().simulator:
                self.assertEqual(properties, None)

    def test_qobj_headers_in_result_sims(self):
        """Test that the qobj headers are passed onto the results for sims."""
        backend = self.provider.get_backend('ibmq_qasm_simulator')

        custom_qobj_header = {'x': 1, 'y': [1, 2, 3], 'z': {'a': 4}}
        circuits = transpile(self.qc1, backend=backend)

        # TODO Use circuit metadata for individual header when terra PR-5270 is released.
        # qobj.experiments[0].header.some_field = 'extra info'

        job = backend.run(circuits, qobj_header=custom_qobj_header)
        result = job.result()
        self.assertTrue(custom_qobj_header.items() <= job.header().items())
        self.assertTrue(custom_qobj_header.items() <= result.header.to_dict().items())
        # self.assertEqual(result.results[0].header.some_field,
        #                  'extra info')

    @slow_test
    @requires_device
    def test_qobj_headers_in_result_devices(self, backend):
        """Test that the qobj headers are passed onto the results for devices."""
        custom_qobj_header = {'x': 1, 'y': [1, 2, 3], 'z': {'a': 4}}

        # TODO Use circuit metadata for individual header when terra PR-5270 is released.
        # qobj.experiments[0].header.some_field = 'extra info'

        job = backend.run(transpile(self.qc1, backend=backend), qobj_header=custom_qobj_header)
        job.wait_for_final_state(wait=300, callback=self.simple_job_callback)
        result = job.result()
        self.assertTrue(custom_qobj_header.items() <= job.header().items())
        self.assertTrue(custom_qobj_header.items() <= result.header.to_dict().items())
        # self.assertEqual(result.results[0].header.some_field,
        #                  'extra info')

    def test_aliases(self):
        """Test that display names of devices map the regular names."""
        aliased_names = self.provider.backend._aliased_backend_names()

        for display_name, backend_name in aliased_names.items():
            with self.subTest(display_name=display_name,
                              backend_name=backend_name):
                try:
                    backend_by_name = self.provider.get_backend(backend_name)
                except QiskitBackendNotFoundError:
                    # The real name of the backend might not exist
                    pass
                else:
                    backend_by_display_name = self.provider.get_backend(
                        display_name)
                    self.assertEqual(backend_by_name, backend_by_display_name)
                    self.assertEqual(
                        backend_by_display_name.name(), backend_name)

    def test_remote_backend_properties_filter_date(self):
        """Test backend properties filtered by date."""
        backends = self.provider.backends(simulator=False)

        datetime_filter = datetime(2019, 2, 1).replace(tzinfo=None)
        for backend in backends:
            with self.subTest(backend=backend):
                properties = backend.properties(datetime=datetime_filter)
                if isinstance(properties, BackendProperties):
                    last_update_date = properties.last_update_date.replace(tzinfo=None)
                    self.assertLessEqual(last_update_date, datetime_filter)
                else:
                    self.assertEqual(properties, None)

    def test_provider_backends(self):
        """Test provider_backends have correct attributes."""
        provider_backends = {back for back in dir(self.provider.backend)
                             if isinstance(getattr(self.provider.backend, back), IBMBackend)}
        backends = {back.name().lower() for back in self.provider._backends.values()}
        self.assertEqual(provider_backends, backends)

    def test_provider_services(self):
        """Test provider services."""
        services = self.provider.services()
        self.assertIn('backend', services)
        self.assertIsInstance(services['backend'], IBMBackendService)
        self.assertIsInstance(self.provider.service('backend'), IBMBackendService)
        self.assertIsInstance(self.provider.backend, IBMBackendService)

        if 'experiment' in services:
            self.assertIsInstance(self.provider.service('experiment'), IBMExperimentService)
            self.assertIsInstance(self.provider.experiment, IBMExperimentService)
        if 'random' in services:
            self.assertIsInstance(self.provider.service('random'), IBMRandomService)
            self.assertIsInstance(self.provider.random, IBMRandomService)
