# Qiskit IBM Provider

[![License](https://img.shields.io/github/license/Qiskit-Partners/qiskit-ibm.svg?style=popout-square)](https://opensource.org/licenses/Apache-2.0)[![Push-Test](https://github.com/Qiskit-Partners/qiskit-ibm/actions/workflows/main.yml/badge.svg)](https://github.com/Qiskit-Partners/qiskit-ibm/actions/workflows/main.yml)[![](https://img.shields.io/github/release/Qiskit-Partners/qiskit-ibm.svg?style=popout-square)](https://github.com/Qiskit-Partners/qiskit-ibm/releases)[![](https://img.shields.io/pypi/dm/qiskit-ibm.svg?style=popout-square)](https://pypi.org/project/qiskit-ibm/)

**Qiskit** is an open-source SDK for working with quantum computers at the level of circuits, algorithms, and application modules.

This project contains a provider that allows accessing the **[IBM Quantum]**
systems and simulators.

## Installation

> **The Qiskit IBM Provider requires** `qiskit-terra>=0.18.1`!
>
> To ensure you are on the latest version, run:
>
> ```bash
> pip install -U "qiskit-terra>=0.18.1"
> ```

You can install the provider using pip:

```bash
pip install qiskit-ibm
```

## Provider Setup

1. Create an IBM Quantum account or log in to your existing account by visiting the [IBM Quantum login page].

2. Copy (and/or optionally regenerate) your API token from your
   [IBM Quantum account page].

3. Take your token from step 2, here called `MY_API_TOKEN`, and run:

   ```python
   from qiskit_ibm import IBMAccount
   account = IBMAccount()
   account.save_account('MY_API_TOKEN')
   ```

   The command above stores your credentials locally in a configuration file called `qiskitrc`.
   By default, this file is located in `$HOME/.qiskit`, where `$HOME` is your home directory.

### Accessing your IBM Quantum backends

After calling `IBMAccount.save_account()`, your credentials will be stored on disk.
Once they are stored, at any point in the future you can load and use them
in your program simply via:

```python
from qiskit_ibm import IBMAccount
account = IBMAccount()
provider = account.load_account()
backend = provider.get_backend('ibmq_qasm_simulator')
```

Alternatively, if you do not want to save your credentials to disk and only
intend to use them during the current session, you can use:

```python
from qiskit_ibm import IBMAccount
account = IBMAccount()
provider = account.enable_account('MY_API_TOKEN')
backend = provider.get_backend('ibmq_qasm_simulator')
```

By default, all IBM Quantum accounts have access to the same, open project
(hub: `ibm-q`, group: `open`, project: `main`). For convenience, the
`IBMAccount.load_account()` and `IBMAccount.enable_account()` methods will return a provider
for that project. If you have access to other projects, you can use:

```python
account = IBMAccount()
provider_2 = account.get_provider(hub='MY_HUB', group='MY_GROUP', project='MY_PROJECT')
```

## Contribution Guidelines

If you'd like to contribute to IBM Quantum Provider, please take a look at our
[contribution guidelines]. This project adheres to Qiskit's [code of conduct].
By participating, you are expect to uphold to this code.

We use [GitHub issues] for tracking requests and bugs. Please use our [slack]
for discussion and simple questions. To join our Slack community use the
invite link at [Qiskit.org]. For questions that are more suited for a forum we
use the `Qiskit` tag in [Stack Exchange].

## Next Steps

Now you're set up and ready to check out some of the other examples from our
[Qiskit Tutorial] repository.

## Authors and Citation

The Qiskit IBM Quantum Provider is the work of [many people] who contribute to the
project at different levels. If you use Qiskit, please cite as per the included
[BibTeX file].

## License

[Apache License 2.0].


[IBM Quantum]: https://www.ibm.com/quantum-computing/
[IBM Quantum login page]:  https://quantum-computing.ibm.com/login
[IBM Quantum account page]: https://quantum-computing.ibm.com/account
[contribution guidelines]: https://github.com/Qiskit-Partners/qiskit-ibm/blob/main/CONTRIBUTING.md
[code of conduct]: https://github.com/Qiskit-Partners/qiskit-ibm/blob/main/CODE_OF_CONDUCT.md
[GitHub issues]: https://github.com/Qiskit-Partners/qiskit-ibm/issues
[slack]: https://qiskit.slack.com
[Qiskit.org]: https://qiskit.org
[Stack Exchange]: https://quantumcomputing.stackexchange.com/questions/tagged/qiskit
[Qiskit Tutorial]: https://github.com/Qiskit/qiskit-tutorial
[many people]: https://github.com/Qiskit-Partners/qiskit-ibm/graphs/contributors
[BibTeX file]: https://github.com/Qiskit/qiskit/blob/master/Qiskit.bib
[Apache License 2.0]: https://github.com/Qiskit-Partners/qiskit-ibm/blob/main/LICENSE.txt
