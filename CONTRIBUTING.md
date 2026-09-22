# Contributing

Thanks for contributing to IT Records.

## Local setup

```bash
pip install -r requirements.txt
python main.py
```

## Tests

Run the existing checks before submitting changes:

```bash
python test_core.py
python test_gui.py
```

`test_gui.py` opens real PyQt5 widgets and is best run in a GUI-capable environment.

## Pull requests

- Keep changes focused and minimal.
- Update documentation when behavior, commands, or workflows change.
- Do not commit secrets, credentials, or local environment artifacts.
