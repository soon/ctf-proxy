#!/bin/bash

set -e

# This script runs the deployment on the VM via SSH

echo "Deploying CTF services to VM..."
echo ""

# Execute deployment script on the VM
./scripts/ssh-exec.sh "/mnt/shared/scripts/deploy-services.sh"

echo ""
echo "Deployment complete! Services are running on the VM."