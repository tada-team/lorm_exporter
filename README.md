# lorm_exporter

## Install
```bash
pip install git+https://github.com/tada-team/lorm_exporter@v0.1.1
```

```python
# settings.py

INSTALLED_APPS = [
    # ...
    'lorm_exporter',
]
```

## Usage

```bash
python manage.py lorm_exporter [app-label] > models.go
```
or 
```bash
python manage.py lorm_exporter [app-label] [app-label] [app-label] --package [go-package-name] > models.go
```

Default --package value is `models`.

Postprocess result .go file:
```bash
goimports -w models.go
```
or 
```bash
go fmt models.go
```

## Use from go code

See https://github.com/tada-team/lorm
