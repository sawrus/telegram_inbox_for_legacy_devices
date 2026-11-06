#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <fixed IPv4 address>" >&2
    exit 2
fi

ip=$(python3 -c 'import ipaddress, sys; print(ipaddress.IPv4Address(sys.argv[1]))' "$1")
tls_dir=${TLS_DIR:-data/tls}
umask 077
if [ -e "$tls_dir" ]; then
    echo "Refusing to overwrite $tls_dir. Move existing certificates aside first." >&2
    exit 1
fi
mkdir -p "$tls_dir"
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
    -subj '/CN=Telegram Inbox Local CA' \
    -addext 'basicConstraints=critical,CA:TRUE' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -keyout "$tls_dir/ca.key" -out "$tls_dir/ca.crt"
openssl req -new -newkey rsa:2048 -sha256 -nodes \
    -subj '/CN=Telegram Inbox' -keyout "$tls_dir/server.key" -out "$tls_dir/server.csr"
printf '%s\n' 'basicConstraints=critical,CA:FALSE' 'keyUsage=critical,digitalSignature,keyEncipherment' \
    'extendedKeyUsage=serverAuth' "subjectAltName=IP:$ip" > "$tls_dir/server.ext"
openssl x509 -req -in "$tls_dir/server.csr" -CA "$tls_dir/ca.crt" -CAkey "$tls_dir/ca.key" \
    -CAcreateserial -days 397 -sha256 -extfile "$tls_dir/server.ext" -out "$tls_dir/server.crt"
rm "$tls_dir/server.csr" "$tls_dir/server.ext" "$tls_dir/ca.srl"
echo "Certificates created in $tls_dir. Keep ca.key and server.key private."
