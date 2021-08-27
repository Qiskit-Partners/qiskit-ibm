# Migrating from qiskit-ibmq-provider>=0.16

## Installation
The Qiskit IBM Provider is now distributed as a separate PyPI package called `qiskit-ibm`. You can install the provider using pip:

```bash
pip install qiskit-ibm
```

## Breaking Changes
1. The `IBMQ` global variable which was an instance of the `IBMQFactory` has been removed.
1. `IBMQFactory` and `AccountProvider` classes have been removed and the functionality provided by these two classes have been combined and refactored in the new `IBMProvider` class. This class will provide a simplified interface and serve as the entrypoint going forward.

For example, if you are looking to migrate your existing code:

Before
```python
from qiskit import IBMQ
provider = IBMQ.load_account() # loads saved account from disk and default provider (ibm-q, open, main)
simulator_backend = provider.get_backend('ibmq_qasm_simulator')
```
After
```python
from qiskit_ibm import IBMProvider
provider = IBMProvider() # loads saved account from disk and default provider (ibm-q, open, main)
simulator_backend = provider.get_backend('ibmq_qasm_simulator')
```

Follow the provider setup instructions in the [README] to learn more.

A lot of other classes have been renamed but may not be directly used by most users. Please see the [Appendix](#class-name-changes) for a complete list.

## Clean up
1. Uninstall `qiskit-ibmq-provider`:

    ```bash
    pip uninstall qiskit-ibmq-provider
    ```
2. If you are using any of the below environment variables, please rename them.

    | Old Name  | New Name |
    | ------------- | ------------- |
    | QE_TOKEN | QISKIT_IBM_API_TOKEN |
    | QE_URL | QISKIT_IBM_API_URL |
    | QE_HUB | QISKIT_IBM_HUB |
    | QE_GROUP | QISKIT_IBM_GROUP |
    | QE_PROJECT | QISKIT_IBM_PROJECT |

    If you are a contributor or internal user of Qiskit IBM Provider please see the [Appendix] for a complete list of environment variable changes.

[README]: https://github.com/Qiskit-Partners/qiskit-ibm/blob/main/README.md

## Appendix
### Class Name changes

| Old Name  | New Name |
| ------------- | ------------- |
| IBMQ  | None (Removed)  |
| IBMQFactory  | None (Removed) |
| AccountProvider  | None (Removed) |
| IBMQBackend  | IBMBackend |
| IBMQBackendService  | IBMBackendService |
| IBMQJob  | IBMJob |
| IBMQJobManager  | IBMJobManager |
| IBMQRandomService  | IBMRandomService |
| IBMQError | IBMError |
| IBMQProviderError | IBMProviderError |
| IBMQAccountError | None (Removed) |
| IBMQAccountValueError | IBMProviderValueError |
| IBMQAccountCredentialsNotFound | IBMProviderCredentialsNotFound |
| IBMQAccountCredentialsInvalidFormat | IBMProviderCredentialsInvalidFormat |
| IBMQAccountCredentialsInvalidToken | IBMProviderCredentialsInvalidToken |
| IBMQAccountCredentialsInvalidUrl | IBMProviderCredentialsInvalidUrl |
| IBMQAccountMultipleCredentialsFound | None (Removed) |
| IBMQBackendError | IBMBackendError |
| IBMQBackendApiProtocolError | IBMBackendApiProtocolError |
| IBMQBackendValueError | IBMBackendValueError |
| IBMQBackendJobLimitError | IBMBackendJobLimitError |
| IBMQInputValueError | IBMInputValueError |
| IBMQNotAuthorizedError | IBMNotAuthorizedError |
| IBMQApiError | IBMApiError |
| IBMQJobError | IBMJobError |
| IBMQJobApiError | IBMJobApiError |
| IBMQJobFailureError | IBMJobFailureError |
| IBMQJobInvalidStateError | IBMJobInvalidStateError |
| IBMQJobTimeoutError | IBMJobTimeoutError |
| IBMQJobManagerError | IBMJobManagerError |
| IBMQJobManagerInvalidStateError | IBMJobManagerInvalidStateError |
| IBMQJobManagerTimeoutError | IBMJobManagerTimeoutError |
| IBMQJobManagerJobNotFound | IBMJobManagerJobNotFound |
| IBMQManagedResultDataNotAvailable | IBMManagedResultDataNotAvailable |
| IBMQJobManagerUnknownJobSet | IBMJobManagerUnknownJobSet |
| WebsocketIBMQProtocolError | WebsocketIBMProtocolError |
| ApiIBMQProtocolError | ApiIBMProtocolError |

### Environment Variable changes

| Old Name  | New Name |
| ------------- | ------------- |
| QE_TOKEN | QISKIT_IBM_API_TOKEN |
| QE_URL | QISKIT_IBM_API_URL |
| QE_HUB | QISKIT_IBM_HUB |
| QE_GROUP | QISKIT_IBM_GROUP |
| QE_PROJECT | QISKIT_IBM_PROJECT |
| QE_HGP | QISKIT_IBM_HGP |
| QE_PRIVATE_HGP | QISKIT_IBM_PRIVATE_HGP |
| QE_DEVICE | QISKIT_IBM_DEVICE |
| USE_STAGING_CREDENTIALS | QISKIT_IBM_USE_STAGING_CREDENTIALS |
| QE_STAGING_TOKEN | QISKIT_IBM_STAGING_API_TOKEN |
| QE_STAGING_URL | QISKIT_IBM_STAGING_API_URL |
| QE_STAGING_HGP | QISKIT_IBM_STAGING_HGP |
| QE_STAGING_PRIVATE_HGP | QISKIT_IBM_STAGING_PRIVATE_HGP |
| QE_STAGING_DEVICE | QISKIT_IBM_STAGING_DEVICE |
| TWINE_PASSWORD | PYPI_API_TOKEN |
