# Provider Health and Failure Visibility Design

日期：2026-08-05

## Problem

真实 A 股 qualification 使用现有 AkShare fetcher chain 时可能长时间等待，
而 runner 只有在全部 case 结束后才落盘聚合产物。这样无法区分已完成证据、
超时、被中止和未开始的 case，也无法安全地继续下一轮 field-level
qualification。

## Chosen design

`g1-provider-health-and-failure-visibility` 在 qualification runner 外层增加
独立进程执行边界：

- live CLI 默认每个 probe case 使用 child process 和显式 timeout；
- 超时后 terminate，短 grace period 后 kill，并记录
  `source_failed + failure_class=timeout + terminated=true`；
- direct mode 保留给 fixture/单元测试，避免测试闭包必须可 pickle；
- 不自动 retry、不改变 provider eligibility、不写 canonical production snapshot；
- 每个 case 完成后追加 `events.ndjson`，并原子更新 partial manifest；
- 中断或超时的 run 标记 incomplete，不能生成或宣称 completed qualification。

## Artifact contract

terminal event 至少包含 run_id、provider、method、ticker、execution mode、status、
elapsed seconds；失败信息只保留 bounded、redacted、non-sensitive metadata。

partial manifest 区分 completed、timed-out、interrupted、not-started cases，并保留
stop reason。只有全部 case 完成后才写现有 aggregate evidence/comparison artifacts。

## Scope boundary

本设计不处理 provider-native retry/backoff、并发调度、LongPort/Longbridge
production、字段 promotion、ranking、legacy cache、G1 capability Gate 或 G2/G3。
真实 probe 通过后仍必须独立做 field-level qualification decision。

## Verification

实现前置 OpenSpec 制品：

`openspec/changes/g1-provider-health-and-failure-visibility/`

已完成 strict validation；implementation tasks 将覆盖 direct/isolated execution、
timeout termination、partial artifacts、redaction、production-path isolation 和
bounded real baseline probe。
