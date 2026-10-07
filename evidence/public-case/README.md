# Public case evidence / 公开案例取证

This is a compact review subset of the original full-film case. It contains all 46 inputs referenced by [`metrics.json`](../metrics.json), with exact byte sizes and SHA-256 values, plus all 149 historical Python/Swift source scripts from the case `work/` directory and the frozen original `video-link-redactor` Skill. See [`index.json`](index.json) for every published file and its metrics record mapping.

这是供网页复查的轻量取证包：46 个指标输入均逐字节对应原统计快照，145 个案例脚本与 4 个原实现脚本全部保留。历史脚本含当时的机器路径和案例专用补丁，应作为取证记录阅读；可复用入口是仓库根目录的 `SKILL.md` 与 `scripts/`。

## Catalog is not an upload / 清单不等于媒体已上传

[`full-review-file-catalog.json`](../full-review-file-catalog.json) and [`full-review-validation.json`](../full-review-validation.json) are unchanged copies of the complete local review bundle's inventory and validation. That bundle contains 3,573 files and 68,516,873,763 logical bytes, including the original film, intermediate renders, final outputs, sources, and review reproductions. The original full film and historical large media remain local; the inventory does **not** imply that those files are downloadable from this repository.

完整本地包仍然包含原片、历史中间视频、最终视频和复查产物。公开清单用于核对完整性，不要求另一台机器下载约 68.5 GB，也不代表这些大媒体已上传。请使用仓库发布页上的一分钟样片进行轻量试用。

## What can be checked online

- Follow `metrics_input_indexes` in `index.json` into the unchanged parent `metrics.json`; each source file's bytes and SHA-256 were verified before copying.
- Read original render logs and report records to check job times and claimed scope. Those job times do not establish an end-to-end wall-clock duration.
- Compare historical source implementations and case-specific patches with the separately maintained portable Skill.
- Read the exact full-bundle catalog while keeping large historical media on the original machine.

Copied text was screened for private-key blocks, GitHub/provider token patterns, JWTs, quoted credential assignments, and credential query strings. No candidate matched. This is a bounded pattern scan, not proof that every conceivable credential format is absent. No raw conversation logs or credential configuration were copied.
