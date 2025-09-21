#!/bin/bash

set -e

SERVICES_DIR="/home/vagrant/services"
EXAMPLES_DIR="/mnt/shared/examples"

echo "CTF Services Deployment Script"
echo "=============================="
echo ""

# Create services directory if it doesn't exist
echo "Creating services directory..."
mkdir -p "$SERVICES_DIR"

# List of services to deploy
SERVICES=(
    "faustctf-2024-quickr-maps"
    "faustctf-2024-secretchannel"
    "faustctf-2024-todo-list-service"
    "faustctf-2024-asm_chat"
)

# Deploy each service
for SERVICE in "${SERVICES[@]}"; do
    echo ""
    echo "Deploying $SERVICE..."
    echo "----------------------"

    SERVICE_PATH="$EXAMPLES_DIR/$SERVICE"
    DEPLOY_PATH="$SERVICES_DIR/$SERVICE"

    if [ ! -d "$SERVICE_PATH" ]; then
        echo "  ✗ Service directory not found: $SERVICE_PATH"
        continue
    fi

    # Copy service to deployment location
    echo "  → Copying service files..."
    rm -rf "$DEPLOY_PATH"
    cp -r "$SERVICE_PATH" "$DEPLOY_PATH"

    # Change to service directory
    cd "$DEPLOY_PATH"

    # Check if Makefile exists and has install target
    if [ -f "Makefile" ]; then
        if grep -q "^install:" Makefile; then
            echo "  → Running make install..."
            make install || echo "  ⚠ Make install failed, continuing..."
        else
            echo "  → No install target in Makefile, skipping..."
        fi
    fi

    # Stop existing containers
    if [ -f "docker-compose.yml" ]; then
        echo "  → Stopping existing containers..."
        docker compose down || true

        echo "  → Starting service containers..."
        docker compose up -d

        # Check service status
        sleep 2
        if docker compose ps | grep -q "Up"; then
            echo "  ✓ Service $SERVICE is running"

            # Get exposed ports
            echo "  → Exposed ports:"
            docker compose ps --format "table {{.Service}}\t{{.Ports}}" | tail -n +2 | sed 's/^/    /'
        else
            echo "  ✗ Service $SERVICE failed to start"
            docker compose logs --tail=20
        fi
    else
        echo "  ⚠ No docker-compose.yml found, skipping container management"
    fi
done

echo ""
echo "=============================="
echo "Service deployment complete!"
echo ""
echo "Deployed services location: $SERVICES_DIR"
echo ""
echo "To check all running services:"
echo "  cd $SERVICES_DIR && for d in */; do echo \$d; cd \$d && docker compose ps && cd ..; done"
echo ""
echo "To stop all services:"
echo "  cd $SERVICES_DIR && for d in */; do cd \$d && docker compose down && cd ..; done"
echo ""
echo "To view logs for a service:"
echo "  cd $SERVICES_DIR/<service-name> && docker compose logs -f"