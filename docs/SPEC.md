# MAZACOIN WALLET — requirements spec (Sami directive, 2026-11-16)

Verbatim requirements from Sami's project specification (phases 4–8 and the
development rules; governing document for this repo's roadmap). The existing
native stack is the implementation vehicle — see SPEC-AUDIT.md for the
compliance matrix and docs/DECISIONS.md for inherited chain parameters.

## PHASE 4 — SECURITY REQUIREMENTS

Security is a primary development requirement. Implement:

1. Local private-key custody.
2. Encrypted wallet storage.
3. Secure seed generation and recovery.
4. Operating-system secure storage where available.
5. PIN or biometric wallet unlocking where supported.
6. Automatic wallet locking after inactivity.
7. Protection against accidental private-key exposure.
8. Secure transaction signing.
9. Input validation and address verification.
10. Protection against malicious transaction construction.

Private keys and recovery seeds must never be transmitted to external
servers, analytics services, or third-party APIs.

Never log private keys, recovery seeds, or unencrypted wallet secrets.

Do not implement custodial wallet infrastructure.

## PHASE 5 — MOBILE APPLICATION EXPERIENCE

Polished, modern fintech interface. Native Mazacoin branding. Simple
navigation. Dark AND light display modes. Mobile-first responsive layout.
Large readable balance display. Easy QR scanning. Minimal send/receive
steps. Clear transaction confirmations.

Primary navigation: 1. Dashboard 2. Send 3. Receive 4. Transactions
5. Wallet Management 6. Settings. Intuitive for ordinary users without
technical blockchain knowledge.

## PHASE 6 — BLOCKCHAIN CONNECTIVITY

Determine the most reliable way to connect directly to the Mazacoin
blockchain. Evaluate: existing Mazacoin full-node software, compatible RPC
interfaces, existing blockchain explorers, available public infrastructure,
lightweight synchronization options, self-hosted infrastructure.

Prefer a decentralized architecture that does not depend on a single
centralized service. If an RPC backend is required, separate it from the
mobile application and document its security requirements.

Do not introduce a new blockchain, token contract, wrapped asset, or
substitute network. The wallet must interact with actual native Mazacoin.

## PHASE 7 — TESTING AND VALIDATION

Before declaring the project complete, verify: new wallet creation, wallet
import and restoration, address generation, address validation, balance
retrieval, transaction history, transaction construction, transaction
signing, transaction broadcasting, QR generation and scanning, encrypted
wallet persistence, application restart and recovery, network interruption
and reconnection, error handling, mobile build compatibility.

Use Mazacoin testnet or a controlled testing environment where available.
Never test by broadcasting unauthorized or unintended mainnet transactions.
Document all functionality that remains incomplete.

## PHASE 8 — FINAL DELIVERABLES

1. Refactored Mazacoin wallet source code. 2. Standalone mobile application
structure. 3. Working wallet dashboard. 4. Native Mazacoin blockchain
integration. 5. Secure wallet creation and restoration. 6. Send and receive
functionality. 7. Transaction history. 8. Build and deployment
instructions. 9. Dependency and licensing report. 10. Security assessment.
11. Testing report. 12. List of outstanding development requirements.

Produce an installable Android APK if the existing technology stack supports
it. Maintain iOS compatibility as a secondary objective if supported by the
architecture.

## IMPORTANT DEVELOPMENT RULES

RULE 1: Do not start from scratch unless the existing architecture is
demonstrably unsuitable.
RULE 2: Do not overwrite or delete existing working project files without a
backup.
RULE 3: Do not substitute Maza-S, Avalanche tokens, wrapped Mazacoin, or
another cryptocurrency for native Mazacoin.
RULE 4: Do not introduce AtomicDEX trading functionality, order books,
swaps, or exchange infrastructure into the core application. Such features
may be considered as future independent modules.
RULE 5: Do not fabricate blockchain connectivity or display simulated
balances as real wallet data.
RULE 6: Do not claim production readiness until actual blockchain
connectivity, transaction signing, broadcasting, and recovery have been
tested.
RULE 7: Keep the code modular, maintainable, documented, and suitable for
future development.
RULE 8: Only reuse components that are technically compatible, appropriately
licensed, secure, and necessary for the Mazacoin wallet. Review all
third-party dependencies and their licenses before incorporation. Keep the
wallet independent of Komodo infrastructure unless a specific integration is
deliberately justified.
