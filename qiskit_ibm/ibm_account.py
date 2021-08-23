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

"""Factory and Account manager for IBM Quantum."""

import logging
from typing import Dict, List, Union, Callable, Optional, Any
from collections import OrderedDict
import traceback

from .api.clients import AuthClient, VersionClient
from .apiconstants import QISKIT_IBM_API_URL
from .credentials import Credentials, discover_credentials
from .credentials.hubgroupproject import HubGroupProject
from .credentials.configrc import (read_credentials_from_qiskitrc,
                                   remove_credentials,
                                   store_credentials)
from .credentials.exceptions import HubGroupProjectInvalidStateError
from .exceptions import (IBMAccountError, IBMAccountValueError, IBMProviderError,
                         IBMAccountCredentialsInvalidFormat, IBMAccountCredentialsNotFound,
                         IBMAccountCredentialsInvalidUrl, IBMAccountCredentialsInvalidToken)
from .ibm_provider import IBMProvider

logger = logging.getLogger(__name__)


class IBMAccount:
    """Account manager for IBM Quantum"""

    def __init__(self) -> None:
        """IBMAccount constructor."""
        self._credentials = None  # type: Optional[Credentials]
        self._providers = OrderedDict()  # type: Dict[HubGroupProject, IBMProvider]
        self._auth_client = None  # type: AuthClient
        self._service_urls = None  # type: Dict[str, str]
        self._user_hubs = None  # type: List[Dict[str, str]]
        self._preferences = None  # type: Optional[Dict]

    # Account management functions.

    def enable(
            self,
            token: str,
            url: str = QISKIT_IBM_API_URL,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None,
            **kwargs: Any
    ) -> Optional[IBMProvider]:
        """Authenticate against IBM Quantum for use during the session.

        Args:
            token: IBM Quantum token.
            url: URL for the IBM Quantum authentication server.
            hub: Name of the hub to use.
            group: Name of the group to use.
            project: Name of the project to use.
            **kwargs: Additional settings for the connection:

                * proxies (dict): proxy configuration.
                * verify (bool): verify the server's TLS certificate.

        Returns:
            If `hub`, `group`, and `project` are specified, the corresponding provider
            is returned. Otherwise the provider for the open access project is returned.

        Raises:
            IBMAccountError: If an IBM Quantum account is already in
                use for the session.
            IBMAccountCredentialsInvalidUrl: If the URL specified is not
                a valid IBM Quantum authentication URL.
            IBMProviderError: If no provider matches the specified criteria,
                or more than one provider matches the specified criteria.
        """
        # Check if an IBM Quantum account is already in use.
        if self._credentials:
            raise IBMAccountError(
                'An IBM Quantum account is already in use for the session.')

        # Check the version used by these credentials.
        credentials = Credentials(token, url, **kwargs)
        version_info = self._check_api_version(credentials)

        # Check the URL is a valid authentication URL.
        if not version_info['new_api'] or 'api-auth' not in version_info:
            raise IBMAccountCredentialsInvalidUrl(
                'The URL specified ({}) is not an IBM Quantum authentication URL. '
                'Valid authentication URL: {}.'.format(credentials.url, QISKIT_IBM_API_URL))

        # Initialize the providers.
        self._initialize_providers(credentials)

        # Prevent edge case where no hubs are available.
        providers = self.providers()
        if not providers:
            logger.warning('No Hub/Group/Projects could be found for this '
                           'account.')
            return None

        # The provider for the default open access project.
        default_provider = providers[0]

        # If any `hub`, `group`, or `project` is specified, return the corresponding provider.
        if any([hub, group, project]):
            default_provider = self.provider(hub=hub, group=group, project=project)

        return default_provider

    def disable(self) -> None:
        """Disable the account currently in use for the session.

        Raises:
            IBMAccountCredentialsNotFound: If no account is in use for the session.
        """
        if not self._credentials:
            raise IBMAccountCredentialsNotFound(
                'No IBM Quantum account is in use for the session.')

        self._credentials = None
        self._providers = OrderedDict()
        self._auth_client = None
        self._service_urls = None
        self._user_hubs = None
        self._preferences = None

    def load(self) -> Optional[IBMProvider]:
        """Authenticate against IBM Quantum from stored credentials.

        Returns:
            If the configuration file specifies a default provider, it is returned.
            Otherwise the provider for the open access project is returned.

        Raises:
            IBMAccountCredentialsInvalidFormat: If the default provider stored on
                disk could not be parsed.
            IBMAccountCredentialsNotFound: If no IBM Quantum credentials
                can be found.
            IBMAccountCredentialsInvalidUrl: If invalid IBM Quantum
                credentials are found.
            IBMProviderError: If the default provider stored on disk could not
                be found.
        """
        # Check for valid credentials.
        try:
            stored_credentials, preferences = discover_credentials()
        except HubGroupProjectInvalidStateError as ex:
            raise IBMAccountCredentialsInvalidFormat(
                'Invalid provider (hub/group/project) data found {}'.format(str(ex))) from ex

        credentials_list = list(stored_credentials.values())

        if not credentials_list:
            raise IBMAccountCredentialsNotFound('No IBM Quantum credentials found.')

        credentials = credentials_list[0]
        # Explicitly check via a server call, to allow environment auth URLs
        # contain IBM Quantum v2 URL (but not auth) slipping through.
        version_info = self._check_api_version(credentials)

        # Check the URL is a valid authentication URL.
        if not version_info['new_api'] or 'api-auth' not in version_info:
            raise IBMAccountCredentialsInvalidUrl(
                'Invalid IBM Quantum credentials found.')

        # Initialize the providers.
        if self._credentials:
            # For convention, emit a warning instead of raising.
            logger.warning('Credentials are already in use. The existing '
                           'account in the session will be replaced.')
            self.disable()

        self._initialize_providers(credentials, preferences)

        # Prevent edge case where no hubs are available.
        providers = self.providers()
        if not providers:
            logger.warning('No Hub/Group/Projects could be found for this account.')
            return None

        # The provider for the default open access project.
        default_provider = providers[0]

        # If specified, attempt to get the provider stored for the account.
        if credentials.default_provider:
            hub, group, project = credentials.default_provider.to_tuple()
            try:
                default_provider = self.provider(hub=hub, group=group, project=project)
            except IBMProviderError as ex:
                raise IBMProviderError('The default provider (hub/group/project) stored on '
                                       'disk could not be found: {}.'
                                       'To overwrite the default provider stored on disk, use '
                                       'the save(overwrite=True) method and specify the '
                                       'default provider you would like to save.'
                                       .format(str(ex))) from None

        return default_provider

    @staticmethod
    def save(
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
            IBMAccountCredentialsInvalidUrl: If the `url` is not a valid
                IBM Quantum authentication URL.
            IBMAccountCredentialsInvalidToken: If the `token` is not a valid
                IBM Quantum token.
            IBMAccountValueError: If only one or two parameters from `hub`, `group`,
                `project` are specified.
        """
        if url != QISKIT_IBM_API_URL:
            raise IBMAccountCredentialsInvalidUrl(
                'Invalid IBM Quantum credentials found.')

        if not token or not isinstance(token, str):
            raise IBMAccountCredentialsInvalidToken(
                'Invalid IBM Quantum token '
                'found: "{}" of type {}.'.format(token, type(token)))

        # If any `hub`, `group`, or `project` is specified, make sure all parameters are set.
        if any([hub, group, project]) and not all([hub, group, project]):
            raise IBMAccountValueError('The hub, group, and project parameters must all be '
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
    def delete() -> None:
        """Delete the saved account from disk.

        Raises:
            IBMAccountCredentialsNotFound: If no valid IBM Quantum
                credentials can be found on disk.
            IBMAccountCredentialsInvalidUrl: If invalid IBM Quantum
                credentials are found on disk.
        """
        stored_credentials, _ = read_credentials_from_qiskitrc()
        if not stored_credentials:
            raise IBMAccountCredentialsNotFound(
                'No IBM Quantum credentials found on disk.')

        credentials = list(stored_credentials.values())[0]

        if credentials.url != QISKIT_IBM_API_URL:
            raise IBMAccountCredentialsInvalidUrl(
                'Invalid IBM Quantum credentials found on disk. ')

        remove_credentials(credentials)

    @staticmethod
    def saved() -> Dict[str, str]:
        """List the account saved on disk.

        Returns:
            A dictionary with information about the account stored on disk.

        Raises:
            IBMAccountCredentialsInvalidUrl: If invalid IBM Quantum
                credentials are found on disk.
        """
        stored_credentials, _ = read_credentials_from_qiskitrc()
        if not stored_credentials:
            return {}

        credentials = list(stored_credentials.values())[0]

        if credentials.url != QISKIT_IBM_API_URL:
            raise IBMAccountCredentialsInvalidUrl(
                'Invalid IBM Quantum credentials found on disk.')

        return {
            'token': credentials.token,
            'url': credentials.url
        }

    def active(self) -> Optional[Dict[str, str]]:
        """Return the IBM Quantum account currently in use for the session.

        Returns:
            Information about the account currently in the session.
        """
        if not self._credentials:
            # Return None instead of raising, maintaining the same behavior
            # of the classic active_accounts() method.
            return None

        return {
            'token': self._credentials.token,
            'url': self._credentials.url,
        }

    # Provider management functions.

    def providers(
            self,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None
    ) -> List[IBMProvider]:
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

        providers = [provider for key, provider in self._providers.items()
                     if all(f(key) for f in filters)]

        return providers

    def provider(
            self,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None
    ) -> IBMProvider:
        """Return a provider for a single hub/group/project combination.

        Args:
            hub: Name of the hub.
            group: Name of the group.
            project: Name of the project.

        Returns:
            A provider that matches the specified criteria.

        Raises:
            IBMProviderError: If no provider matches the specified criteria,
                or more than one provider matches the specified criteria.
        """
        providers = self.providers(hub, group, project)

        if not providers:
            raise IBMProviderError('No provider matches the specified criteria: '
                                   'hub = {}, group = {}, project = {}'
                                   .format(hub, group, project))
        if len(providers) > 1:
            raise IBMProviderError('More than one provider matches the specified criteria.'
                                   'hub = {}, group = {}, project = {}'
                                   .format(hub, group, project))

        return providers[0]

    # Private functions.

    @staticmethod
    def _check_api_version(credentials: Credentials) -> Dict[str, Union[bool, str]]:
        """Check the version of the remote server in a set of credentials.

        Returns:
            A dictionary with version information.
        """
        version_finder = VersionClient(credentials.base_url,
                                       **credentials.connection_parameters())
        return version_finder.version()

    def _initialize_providers(
            self, credentials: Credentials,
            preferences: Optional[Dict] = None
    ) -> None:
        """Authenticate against IBM Quantum and populate the providers.

        Args:
            credentials: Credentials for IBM Quantum.
            preferences: Account preferences.
        """
        self._auth_client = AuthClient(credentials.token,
                                       credentials.base_url,
                                       **credentials.connection_parameters())
        self._service_urls = self._auth_client.current_service_urls()
        self._user_hubs = self._auth_client.user_hubs()
        self._preferences = preferences or {}
        self._credentials = credentials

        for hub_info in self._user_hubs:
            # Build the provider.
            try:
                provider = IBMProvider(token=credentials.token, **hub_info, account=self)
                self._providers[provider.credentials.unique_id()] = provider
            except Exception:  # pylint: disable=broad-except
                # Catch-all for errors instantiating the provider.
                logger.warning('Unable to instantiate provider for %s: %s',
                               hub_info, traceback.format_exc())
