#!/bin/bash

set -e

# This script runs the deployment on the VM via SSH

echo "Deploying CTF services to VM..."
echo ""

# Execute deployment script on the VM
"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ssh-exec.sh" "/mnt/shared/scripts/deploy-services.sh"

echo ""
echo "Deployment complete! Services are running on the VM."