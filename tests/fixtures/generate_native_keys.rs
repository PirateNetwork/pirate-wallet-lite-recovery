// Synthetic fixtures only. Both mnemonic phrases below are public BIP39 vectors.
// This program does not open or discover wallet files and accepts only an output path.
use pirate_core::keys::ExtendedSpendingKey;
use pirate_params::NetworkType;
use std::fmt::Write as _;
use std::io::Write as _;

const PRIMARY: &str = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon art";
const IMPORTED: &str = "legal winner thank year wave sausage worth useful legal winner thank year wave sausage worth useful legal winner thank year wave sausage worth title";

fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes { write!(&mut s, "{b:02x}").unwrap(); }
    s
}

#[allow(deprecated)]
fn key_json(label: &str, mnemonic: &str, account: u32) -> String {
    let sk = ExtendedSpendingKey::from_mnemonic_with_account(
        mnemonic, NetworkType::Mainnet, account,
    ).expect("public BIP39 vector must derive");
    let sk_bytes = sk.to_bytes();
    assert_eq!(sk_bytes.len(), 169);
    let xfvk = sk.inner().to_extended_full_viewing_key();
    let mut xfvk_bytes = Vec::new();
    xfvk.write(&mut xfvk_bytes).expect("xFVK serialization");
    assert_eq!(xfvk_bytes.len(), 169);
    let sk_bech32 = zcash_client_backend::encoding::encode_extended_spending_key(
        "secret-extended-key-main", sk.inner(),
    );
    let xfvk_bech32 = sk.to_xfvk_bech32_for_network(NetworkType::Mainnet);
    let address = sk.to_extended_fvk().derive_address(0).encode();
    format!(
        "{{\"label\":\"{label}\",\"account\":{account},\"mnemonic\":\"{mnemonic}\",\"sk_hex\":\"{}\",\"xfvk_hex\":\"{}\",\"sk_bech32\":\"{sk_bech32}\",\"xfvk_bech32\":\"{xfvk_bech32}\",\"address\":\"{address}\"}}",
        hex(&sk_bytes), hex(&xfvk_bytes),
    )
}

fn main() {
    let output = std::env::args().nth(1).expect("explicit synthetic fixture output path");
    let content = format!(
        "{{\"synthetic_public_vectors_only\":true,\"network\":\"mainnet\",\"primary_entropy_hex\":\"{}\",\"imported_entropy_hex\":\"{}\",\"keys\":[{},{},{}]}}\n",
        "00".repeat(32), "7f".repeat(32),
        key_json("primary_account_0", PRIMARY, 0),
        key_json("primary_account_7", PRIMARY, 7),
        key_json("imported_account_0", IMPORTED, 0),
    );
    let mut file = std::fs::OpenOptions::new().write(true).create_new(true)
        .open(&output).expect("create a new synthetic fixture only");
    file.write_all(content.as_bytes()).expect("write synthetic fixture");
    println!("Wrote synthetic public fixture: {output}");
}
