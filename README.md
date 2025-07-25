# TD

Official implementation of the paper:  
**TD: Faster Asynchronous BFT Protocol without Throughput-Latency Tension**

<p align="center">
<img width="800" alt="TD illustration" src="https://github.com/user-attachments/assets/890ad71e-d851-47d4-ad10-5c98c4fa3eb9" />
</p>

## Project Structure

dumbotd_2 contains the proposed method TD（dumbotd and dumbotd_1are for testing purposes）

## Clone the Repository
```bash
git clone https://github.com/tzslg/TD.git
cd TD
```

## Requirements

- **Local Environment**: Ubuntu 20.04.3-desktop-amd64, Python 3.10  
- **AWS Environment**: Ubuntu 20.04.3 LTS, Python 3.10  
  - Instance Specifications: 2 vCPUs, 4 GB RAM, 10 Gbps bandwidth

- **Performance Evaluation**: Tested at 3 scales with node counts: 4, 16, and 64

Other dependencies are listed below.

## Install Environment
### Dependencies:
```bash
sudo apt-get update
sudo apt-get -y install make bison flex libgmp-dev libmpc-dev python3 python3-dev python3-pip libssl-dev

wget https://crypto.stanford.edu/pbc/files/pbc-0.5.14.tar.gz
tar -xvf pbc-0.5.14.tar.gz
cd pbc-0.5.14
sudo ./configure
sudo make
sudo make install
cd ..

sudo ldconfig /usr/local/lib

cat <<EOF >/home/ubuntu/.profile
export LIBRARY_PATH=$LIBRARY_PATH:/usr/local/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib
EOF

source /home/ubuntu/.profile
export LIBRARY_PATH=$LIBRARY_PATH:/usr/local/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib
 
git clone https://github.com/JHUISI/charm.git
cd charm
sudo ./configure.sh
sudo make
sudo make install
sudo make test
cd ..

python3 -m pip install --upgrade pip
sudo pip3 install gevent setuptools gevent numpy ecdsa pysocks gmpy2 zfec gipc pycrypto coincurve
```
### Quick Start

To run **TD** locally:

1. Modify the `run_local_network_test.sh` script by replacing the node startup section with the following:
   ```bash
   rm -rf ./log/
   killall python3
   i=0
   while [ "$i" -lt $1 ]; do
       echo "start node $i..."
       python3 run_socket_node.py --sid 'sidA' --id $i --N $1 --f $2 --B $3 --S 100 --P "td_2" --D True --O True --C $4 &
       i=$(( i + 1 ))
   done
    ```
2. Then execute the script with your desired parameters.

   For example:
   ```bash
      ./run_local_network_test.sh 4 1 2000 50
   ```
This will launch a local test of TD with 4 nodes, 1 tolerated faulty node (f=1), a batch size of 2000 transactions, and run for 50-epoch warm up.

### Run on AWS Cloud Servers:
Example: Setting up remote nodes and starting protocols
Configure IPs and credentials

Distribute hosts.config to all nodes

Remotely launch the TD protocol across servers

#### Dependencies:
```bash
sudo apt-get update
sudo apt-get -y install make bison flex libgmp-dev libmpc-dev python3 python3-dev python3-pip libssl-dev

wget https://crypto.stanford.edu/pbc/files/pbc-0.5.14.tar.gz
tar -xvf pbc-0.5.14.tar.gz
cd pbc-0.5.14
sudo ./configure
sudo make
sudo make install
cd ..

sudo ldconfig /usr/local/lib

cat <<EOF >/home/ubuntu/.profile
export LIBRARY_PATH=$LIBRARY_PATH:/usr/local/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib
EOF

source /home/ubuntu/.profile
export LIBRARY_PATH=$LIBRARY_PATH:/usr/local/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib
 
git clone https://github.com/JHUISI/charm.git
cd charm
sudo ./configure.sh
sudo make
sudo make install
sudo make test
cd ..

python3 -m pip install --upgrade pip
sudo pip3 install gevent setuptools gevent numpy ecdsa pysocks gmpy2 zfec gipc pycrypto coincurve

git clone --branch master https://github.com/tzslg/TD.git
```

#### Upload hosts.config to AWS servers:
```bash
#!/bin/bash
N=4
pubIPsVar=([0]='44.204.31.112'
[1]='13.211.202.171'
[2]='52.195.211.111'
[3]='3.248.251.99'
)
# private IPs --- This is the private IPs of AWS servers
priIPsVar=([0]='172.31.83.243'
[1]='172.31.43.24'
[2]='172.31.42.162'
[3]='172.31.3.77'
)
# xxx.pem is the SSH private key used for the EC2 instance in AWS.
pem=(
[0]="math1.pem"
[1]="math2.pem"
[2]="math3.pem"
[3]="math4.pem"
)

rm tmp_hosts.config
i=0;while [ $i -le $(( N-1 )) ]; do
    echo $i ${priIPsVar[$i]} ${pubIPsVar[$i]} $(($((607*$i))+5000)) >> tmp_hosts.config
    i=$(( i+1 ))
done

i=0;while [ $i -le $(( N-1 )) ]; do
    ssh -o "StrictHostKeyChecking no" -i ${pem[i]} ubuntu@${pubIPsVar[i]} "rm /home/ubuntu/TD/hosts.config"
    scp -i ${pem[i]} tmp_hosts.config ubuntu@${pubIPsVar[i]}:/home/ubuntu/TD/hosts.config &
    i=$(( i+1 ))
done
```
#### Kill all Python processes:
```bash
i=0;while [ $i -le $(( N-1 )) ]; do
    ssh -o "StrictHostKeyChecking no" -i ${pem[i]} ubuntu@${pubIPsVar[i]} "sudo killall -9 python3"
    i=$(( i+1 ))
done
```

#### Start protocol on all servers:
```bash
i=0;while [ $i -le $(( N-1 )) ]; do
    ssh -o "StrictHostKeyChecking no" -i ${pem[i]} ubuntu@${pubIPsVar[i]} "rm -rf /home/ubuntu/TD/log/"
    i=$(( i+1 ))
done

# Start Protocols at all remote AWS servers
i=0;while [ $i -le $(( N-1 )) ]; do
    ssh -i ${pem[i]} ubuntu@${pubIPsVar[i]} "
    export LIBRARY_PATH=$LIBRARY_PATH:/usr/local/lib; 
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib; 
    cd /home/ubuntu/TD; 
    nohup python3 run_socket_node.py --sid 'sidA' --id $i --N $N --f $(((N-1)/3)) --B 1000 --S 100 --P "td_2"  --C 20 > node-$i.out" &
    i=$((i+1))
done
```
#### Download results:
```bash
# Download logs from all remote AWS servers to your local PC
i=0;while [ $i -le $(( N-1 )) ]; do
    scp -i ${pem[i]} ubuntu@${pubIPsVar[i]}:/home/ubuntu/TD/log/consensus-node-$i.log node-$i.log &
    i=$(( i+1 ))
done
```
## Acknowledgements

We sincerely thank the authors of the following open-source projects. Their excellent work provided valuable references for this implementation:

- [HoneyBadgerBFT](https://github.com/amiller/HoneyBadgerBFT)  
- [Dumbo_NG](https://github.com/fascy/Dumbo_NG)  
- [dumbo](https://github.com/yylluu/dumbo)  

## Citation
If you find our work useful, please kindly cite as:
```
@article{Pang2025TD,
  title={TD: Faster Asynchronous BFT Protocol without Throughput-Latency Tension},
  author={Zengyu Pang, Ligen Shi, Hua Xiang},
  year={2025}
}
```
## Contact
If you have any questions or suggestions, feel free to contact:

Pang, Email: 2022102010021@whu.edu.cn
