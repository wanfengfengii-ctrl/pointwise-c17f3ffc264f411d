# 正式实测勘误与评分替代

质控员按原报告号查当下可用于复盘的评分，按具体报告号查当时已签的正文和回执。台架封批后，正式勘误可以替换实测值或出处。预测仍用原报告当时所选的固定件。现有 V1 入口、编码、原报告、原实测及原回归保持兼容。各 Store 仍接收由调用者打开的空闲 SQLite 连接，试验、实收和归档各有自己的库。

## 台架发布

在 `bench.closeout` 提供 `publish_amendment(bench, batch_id, parent_id, amendment_id, rows)` 和 `read_amendment(bench, batch_id, amendment_id)`，均返回可直接实收的字典。父号是该批原封批号或已发勘误号。发布按当前链尾承接。重发已存在的同号同内容勘误先按原父件核对，返回原件，即使链尾已经推进。异内容或另开分支报 ValueError。原封批仍由 `close_results` 领取。

勘误字典包含以下字段：

| 字段 | 口径 |
| --- | --- |
| `kind` | `result-amendment` |
| `batch_id`、`roster_id`、`specimens` | 与原封批相同，`specimens` 保持清册顺序 |
| `source_id` | 具名勘误号，同批唯一，沿用 V1 名称规则，`results:` 前缀留给原封批 |
| `parent_id` | 同批原封批或勘误的 `source_id`，不可指向自身 |
| `parent_sha256` | 父件规范正文的 SHA-256 小写十六进制字符串 |
| `rows` | 非空逐片替换清单，每项为 `specimen_id`、整数二值 `outcome` 和非空 `source` |

每片在一次勘误中至多出现一次，必须在清册内。替换行同时给出新值和新出处，其余片沿用父件。行重排等价，输出按清册序。计算指纹时，先按上述规则规范父件的行，V1 原封批沿用 `bench_piece_payload` 的规范字典，再用 `json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)` 的 UTF-8 字节计算。源端写入成功后才可返回新件。

## 质控实收

`evaluation.accession.accept_piece(accessions, payload)` 新增接收正式勘误。格式、清册标识、同号内容及已知父件的清册和指纹须核对。允许连续链的后继先于父件到达，并可在归档库关闭时持久实收。等价重投返回首纳号。已知错配和冲突的新件拒收。以同批、同清册、同父号及同父指纹来件声明同一条父子边的起点，两个不同后继争用这个起点时拒收后到件。先接纳的待证件若随后确认错配，不影响正确父件入库，也不能占用真正父件的后继位置。已接纳的原件重投仍沿用其首纳号。

只有以原封批为根、每条父子关系均通过核对的连续勘误链，才可改变在用评分依据。父件补齐时按当时已实收的连续链确认最末代。补齐多个连续件时，链中间代不需要逐一成为在用依据。`evaluation.accession.amendment_status(accessions, accession_id)` 返回 `pending_proof`、`invalid`、`effective` 或 `superseded`，分别表示缺证、已判错配或承接无效、当前合格末代、已核实但已有后继生效。此入口的已知 V1 接纳号属于错类型。

## 替代签发与在用查询

在 `evaluation.review` 提供 `issue_replacement(accessions, archive, original_report_id, amendment_accession)`。它以原 V1 报告为根，固定原预测接纳号和清册，并只用从该原封批连续承接的同批勘误复算。首次请求须在调用期间具有目标勘误的在用资格。若更晚的实收代次在复算期间生效，已经取得资格的请求可以签存历史件，但不得让旧代恢复在用。已签存的同一原报告和勘误可重领，无须该代仍在用。直接请求一个尚未签存且已经失去资格的旧代须拒绝。

替代沿用现有 `review_reports` 和 `review_receipts` 的编号和签发流水。每个原报告和目标勘误至多签一份。正文、出处、关联和回执同次提交。写入或提交失败传播 SQLite 错误，无本次新增正文、关联或回执，可用原请求重试。此失败不撤销已在实收库生效的勘误。

签发返回与 V1 报告 JSON 同形的字典，字段为 `report_id`、`body`、`receipt`。`body` 沿用 V1 字段和有理数编码，`results_accession` 和 `results_closeout` 指原封批，`rows` 和 `mean` 使用勘误后的实测，另有 `original_report_id`、`amendment_accession` 和 `amendment_chain`。`amendment_chain` 从首勘误排到目标代，每项为 `source_id`、`accession_id`。`archive.lookup.read_replacement(archive, report_id)` 返回这份存值，只需归档库。原 V1 报告继续交给 `read_review`。

在 `evaluation.review` 提供 `read_current_review(accessions, archive, original_report_id)`，返回恰含 `status`、`amendment_accession`、`report` 的字典：

| status | amendment_accession | report |
| --- | --- | --- |
| `original` | `None` | 原 V1 报告 JSON 对应的字典 |
| `pending_recompute` | 当前合格末代的实收号 | `None` |
| `replacement` | 当前合格末代的实收号 | 已提交的对应替代报告字典 |

有生效勘误但对应替代尚未提交时返回 `pending_recompute`。一次在用查询返回的资格代次和归档结果，须在该调用期间的同一时点成立。实收、签发及查询可用不同连接交错调用。迟到的旧代替代可按号审计，不能重新取得在用资格。非法输入、冲突、错类型、错批、错根封批或不具备首次签发资格报 ValueError。未知有效编号报 KeyError。

## 样例和运行

`python3 -B -m examples.amendment_fixture` 生成原报告。清册 B、A，概率分别为 1/3、1/4，原实测分别为 0、1，原分 97/288。勘误一把 A 改为 0，单用第一代应为 25/288。勘误二承接勘误一，把 B 改为 1，完整复算应为 73/288。误跳过勘误一会得到 145/288。

完成功能后可运行 `python3 -B -m examples.amendment_scenarios`，以真实库查看倒序送件、独立实收、待复算、归档失败重试和重开领取。交错核验关注这样一次调用：第一代尚无替代时查询开始，第二代实收推进，第一代签发迟到。若写入按这个顺序发生，查询不能给出从未在用的第一代分数。若实现使这几个事件互斥，核验实际提交顺序以及该顺序下的在用结论。

运行清单沿用 `.pointwise-runtime.json` 的 CLI 版本 1 格式。`setup` 为命令参数数组的列表，`verify` 和 `demo` 各为一条命令的参数数组。完成后让 `verify` 保留 `python3 -B check_project.py` 的全量原回归并核验新链路，任一检查失败时返回非零。让 `demo` 展示上述乱序接纳、待复算和重开领取的业务结果。原 `python3 -B -m examples.workday` 仍可单独运行。
