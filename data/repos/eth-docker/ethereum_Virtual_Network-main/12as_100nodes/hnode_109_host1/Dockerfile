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
COPY f4d556a844298d3911e6d250e4a2d93b /tmp/eth-genesis.json
COPY 2aad2494423b97267f8a17f09efa30ee /tmp/keystore/UTC--2025-06-13T04-01-15.572773000Z--0x36Cbb6bEE031ceeA490b0F7B4c918d41693a1c88
COPY d2cdff8371aa6af79bb63954a87ac69f /tmp/eth-password
COPY 0bf749f51915d190035e14f6afa9a371 /tmp/eth-nodes
COPY 427fecb1e0b6c8dc8f669b5b71b8db71 /tmp/eth-bootstrapper
COPY f43c6ee1f9004436450c6e3e2cbfda4a /tmp/beacon-setup-node
COPY f38a12d2b276c7254e83df35e22f1fc3 /tmp/beacon-bootstrapper
COPY 9859b953a2cc838d867992891cc2b63d /tmp/jwt.hex
CMD ["/start.sh"]

