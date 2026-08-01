# Extending The Evaluation

Researchers can extend this artifact by varying:

- block ranges;
- transaction volume;
- hardware architecture;
- storage engines;
- RPC latency;
- failure models;
- geographic distribution;
- IM replication policies.

## Suggested directions

- larger regtest workloads with the same validation logic;
- alternate local stores such as RocksDB or LevelDB;
- multiple physical nodes for real network measurements;
- higher-latency RPC and remote-disk scenarios;
- longer observation horizons for IM retrieval and recovery.

## Reporting guidance

When reporting new results:

- keep functional counts separate from timing metrics;
- label hardware and software versions explicitly;
- separate replicated network storage from local auxiliary-index storage;
- avoid comparing runs with different workloads as if they were equivalent.
