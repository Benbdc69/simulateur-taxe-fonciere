#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export TF_LOCAL_MODE=1
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 est requis : https://www.python.org/downloads/'
  exit 1
fi
if [ ! -f .venv/bin/python ]; then
  echo 'Préparation initiale de l’environnement Python...'
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
