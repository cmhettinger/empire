```mermaid
flowchart LR
  core_run["core_run"]
  storage_root["storage_root"]
  stored_object["stored_object"]

  core_run -->|stored_object_run_id_fkey| stored_object
  storage_root -->|stored_object_storage_root_id_fkey| stored_object
```
