# Public data host 001

This repository hosts approved generated public record representations, not original private holdings. The publication workflow reads public inputs without writing upstream. The first baseline is 6,065 representations and 168,959,761 input bytes. A changed baseline fails closed for review. Every catalog, blob and reconstructed record is hash/length checked before the generated version is committed. Data files are bounded; the dataset and repository have explicit storage budgets.

The workflow writes datasets/build-RUN_ID and published.json. The pointer identifies an immutable dataset commit and collection-manifest hash; clients resolve relative blob/catalog paths against data_base_url. Binary chunks must be concatenated in sequence, verified against the complete representation hash, and then decoded as UTF-8. Source snapshot identities are retained separately in the dataset.

A successful commit is not verification that browser fetches work. The collection's internal publication_status and data_hosts describe the build artifact; published.json is the separate publication descriptor. Do not mistake record counts for independent meetings or complete historical coverage. No source-independent factual certification is provided.

Only this new repository is written by the pipeline. No app deployment, private-source import, automatic creation of further repositories, paid service, or alteration of original archives is included. Further data hosts require explicit approval when measured budgets require them.
