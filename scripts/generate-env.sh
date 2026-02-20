#!/bin/bash
# Generate a .env file with a random ENCRYPTION_KEY.
# Usage: bash scripts/generate-env.sh
set -e

if [ -f .env ]; then
    echo "Error: .env already exists. Remove it first or edit manually."
    exit 1
fi

cp .env.example .env

# Generate a random Fernet key and replace the placeholder
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
if [ "$(uname)" = "Darwin" ]; then
    sed -i '' "s/CHANGE_ME_generate_a_real_fernet_key/$FERNET_KEY/" .env
else
    sed -i "s/CHANGE_ME_generate_a_real_fernet_key/$FERNET_KEY/" .env
fi

echo "Created .env with a fresh ENCRYPTION_KEY."
echo "Next steps:"
echo "  1. Edit .env and set NWS_USER_AGENT with your email address"
echo "  2. Run: docker compose up -d"
