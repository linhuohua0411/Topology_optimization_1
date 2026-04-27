FROM f1d53a66de3c35d8a921558f3b4bdbbd
ARG DEBIAN_FRONTEND=noninteractive
COPY 082b96ec819c95ae773daebde675ef80 /start.sh
COPY d18858afc6bb66ec3a19d872077acfd2 /seedemu_sniffer
COPY 17ac2d812a99a91e7f747e1defb72a29 /seedemu_worker
RUN chmod +x /start.sh
RUN chmod +x /seedemu_sniffer
RUN chmod +x /seedemu_worker
COPY e01e36443f9f72c6204189260d0bd276 /ifinfo.txt
COPY d3d51fdf7f4bad30dc5db560a01ce629 /interface_setup
COPY 10757022df68a4423d62c35e1ce89a22 /tmp/config.yaml
COPY 4673d48a9636c056769c28009c0e1d8b /tmp/validator-ids
COPY 6efed1981b79f83aa06c35aab1e67e23 /tmp/prepare_resource.sh
COPY 029624dc5d70ad6b595f4b4db3060800 /local-testnet/beacon_bootnode_http_server.py
CMD ["/start.sh"]

