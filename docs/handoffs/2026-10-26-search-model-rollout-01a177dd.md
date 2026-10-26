# Approved YouTube search model rollout

更新：2026-10-26（Asia/Taipei）；基準7ad11ec；分支main。
使用者明確同意：僅Google Search查證改用gemini-2.5-flash-lite，影片摘要維持gemini-3.5-flash-lite。
已核對hook ahead=0/behind=0、PROJECT_STATUS、前次reliability handoff、實際YT workflow與Gemini模型路由。tracked files乾淨。
計畫：設定並讀回GitHub GEMINI_SEARCH_MODEL variable，啟動一次正式YT workflow，確認模型/查證/Telegram送達與進度保存。
限制：不改key、不開billing、不關grounding、不清除日配額、不假標pending完成。
狀態：實施中；尚未確認送達。
commit/push：待保存驗證結果。

正式驗證run40319704818/job121561213494失敗：Search模型回HTTP404/model_configuration，觸發scope配置封鎖；狀態保存success。不能稱查證模型已可用。準備以正式key（header，非URL）讀取模型catalog，並回復原設定，避免保留失敗部署。
