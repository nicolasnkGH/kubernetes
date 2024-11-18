import subprocess
import os
import getpass
import yaml

# Function to check if the SSH key already exists, otherwise generate it
def check_and_generate_ssh_key():
    ssh_key_path = os.path.expanduser("~/.ssh/id_rsa")

    if not os.path.exists(ssh_key_path):
        print("SSH key pair not found. Generating a new key pair...")
        subprocess.run(["ssh-keygen", "-t", "rsa", "-b", 4096, "-f", ssh_key_path, "-N", ""])
        print(f"SSH key pair generated: {ssh_key_path}, {ssh_key_path}.pub")
    else:
        print("SSH key pair already exists.")

# Function to distribute the SSH key to the target host
def distribute_ssh_key(host_ip, ssh_user):
    ssh_key_path = os.path.expanduser("~/.ssh/id_rsa.pub")
    print(f"Distributing SSH key to {ssh_user}@{host_ip}...")
    subprocess.run(["ssh-copy-id", "-i", ssh_key_path, f"{ssh_user}@{host_ip}"], check=True)
    print(f"SSH key distributed to {host_ip}.")

# Function to create or update the inventory file for Ansible
def create_or_update_inventory_file():
    inventory_path = "inventory.yaml"

    if os.path.exists(inventory_path):
        use_existing = input("Inventory file 'inventory.yaml' already exists. Do you want to reuse it? (yes/no): ").strip().lower()
        if use_existing == "yes":
            print(f"Using existing inventory file: {inventory_path}")
            return True  # Reuse existing inventory file
        else:
            os.remove(inventory_path)
            print(f"Old inventory file '{inventory_path}' deleted.")
            return False  # Create a new inventory file
    else:
        return False  # Create a new inventory file

# Function to create the inventory file for Ansible
def create_inventory_file():
    hostname = input("Enter node hostname: ").strip()
    host_ip = input("Enter node IP address: ").strip()

    inventory_data = {
        "all": {
            "hosts": {
                hostname: {
                    "ansible_host": host_ip,
                    "ansible_user": "ubuntu",
                    "ansible_become_password": sudo_password
                }
            }
        }
    }

    with open("inventory.yaml", "w") as inventory_file:
        yaml.dump(inventory_data, inventory_file, default_flow_style=False)
    print(f"Inventory file 'inventory.yaml' created.")

# Function to run the Ansible playbook
def run_ansible_playbook(playbook_file):
    ansible_command = f"ansible-playbook {playbook_file} -i inventory.yaml --extra-vars 'ansible_become_password={sudo_password}'"
    print(f"Running the Ansible playbook: {playbook_file}...")
    subprocess.run(ansible_command, shell=True, check=True)

# Function to copy kubeconfig file from remote to local using Ansible playbook
def copy_kubeconfig_from_remote():
    # Run the fetch_kubeconfig playbook to fetch the kubeconfig file
    print("Copying kubeconfig file using Ansible playbook...")
    run_ansible_playbook("fetch_kubeconfig.yaml")
    print(f"Kubeconfig file copied to {os.path.join(os.getcwd(), '.kube/config')}")

# Function to verify Kubernetes API
def verify_kubernetes_api():
    try:
        # Ensure kubeconfig exists
        kubeconfig_path = os.path.join(os.getcwd(), ".kube/config")
        if not os.path.exists(kubeconfig_path):
            print(f"Kubeconfig not found at {kubeconfig_path}. Make sure it is available.")
            return

        # Set the KUBECONFIG environment variable
        os.environ["KUBECONFIG"] = kubeconfig_path

        # Verify Kubernetes API using kubectl
        print("Verifying Kubernetes API connectivity...")
        kubectl_version = subprocess.run(["kubectl", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(f"Kubectl version:\n{kubectl_version.stdout.decode('utf-8')}")

        # Verify Kubernetes API version using curl
        print("Fetching Kubernetes API version via curl...")
        curl_command = f"curl -k https://{host_ip}:6443/version"
        api_version = subprocess.run(curl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(f"Kubernetes API version:\n{api_version.stdout.decode('utf-8')}")
    except subprocess.CalledProcessError as e:
        print(f"Error verifying Kubernetes API:\n{e.stderr.decode('utf-8')}")
        raise

# Main deployment function
def main():
    # Check if SSH key exists and generate if necessary
    check_and_generate_ssh_key()

    # Ask if the user wants to use an existing inventory file or not
    reuse_inventory = create_or_update_inventory_file()

    if not reuse_inventory:
        # Collect deployment details
        mode = input("Choose installation mode (single/cluster): ").strip().lower()
        if mode not in ['single', 'cluster']:
            print("Invalid installation mode.")
            return

        global host_ip
        ssh_user = input("Enter SSH username: ").strip()
        ssh_password = getpass.getpass("Enter SSH password: ").strip()

        # Distribute SSH key to the target node
        host_ip = input("Enter node IP address: ").strip()
        distribute_ssh_key(host_ip, ssh_user)

        # Collect sudo password for Ansible
        global sudo_password
        sudo_password = getpass.getpass("Enter sudo password for Ansible: ").strip()

        # Create a new inventory file if not reusing
        create_inventory_file()

    else:
        # If reusing inventory, load the inventory data
        with open('inventory.yaml', 'r') as inventory_file:
            inventory_data = yaml.safe_load(inventory_file)

        # Check if the expected structure exists
        if "all" in inventory_data and "hosts" in inventory_data["all"]:
            hosts = inventory_data["all"]["hosts"]
            if hosts:
                # Retrieve host details (assuming only one host for simplicity)
                host_name = list(hosts.keys())[0]  # Get the first host name
                host_details = hosts[host_name]
                host_ip = host_details.get("ansible_host", "")
                ssh_user = host_details.get("ansible_user", "ubuntu")
                print(f"Using existing host from inventory: {host_name} - {host_ip}")
            else:
                print("No hosts found in inventory file.")
                return
        else:
            print("Invalid structure in inventory file.")
            return

        # Ask for sudo password for Ansible
        sudo_password = getpass.getpass("Enter sudo password for Ansible: ").strip()

    # Run the dependencies installation playbook first
    run_ansible_playbook("install_dependencies.yaml")

    # Run the Kubernetes installation playbook second
    run_ansible_playbook("install_kubernetes.yaml")

    # Copy the kubeconfig file and set the environment variable
    copy_kubeconfig_from_remote()

    # Verify the Kubernetes API
    verify_kubernetes_api()

if __name__ == "__main__":
    main()