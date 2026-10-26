# Approved YouTube search model rollout

更新：2026-10-26（Asia/Taipei）；基準7ad11ec；分支main。
使用者明確同意：僅Google Search查證改用gemini-2.5-flash-lite，影片摘要維持gemini-3.5-flash-lite。
已核對hook ahead=0/behind=0、PROJECT_STATUS、前次reliability handoff、實際YT workflow與Gemini模型路由。tracked files乾淨。
計畫：設定並讀回GitHub GEMINI_SEARCH_MODEL variable，啟動一次正式YT workflow，確認模型/查證/Telegram送達與進度保存。
限制：不改key、不開billing、不關grounding、不清除日配額、不假標pending完成。
狀態：實施中；尚未確認送達。
commit/push：待保存驗證結果。

正式驗證run40319704818/job121561213494失敗：Search模型回HTTP404/model_configuration，觸發scope配置封鎖；狀態保存success。不能稱查證模型已可用。準備以正式key（header，非URL）讀取模型catalog，並回復原設定，避免保留失敗部署。

模型catalog run40320397547/job121563576036成功，正式key清單明列gemini-2.5-flash-lite與generateContent。因此更正：第一次請求404不能直接判定整個模型不可用。已回復原3.5搜尋設定，沒有啟用帳務或改摘要模型。
新增404模型存在性確認（模型metadata GET200/網路不確定時退避，不永久封鎖；metadata404才配置封鎖），以政策實作revision3重新評估舊誤封鎖且保留當日used；新增YT單writer probe_search測試入口，使用原youtube配額並且不發Telegram。367項完整測試與Ruff通過，準備推送後重新套用使用者已同意的2.5並先probe。

最小probe run40320856263/job121565127005仍HTTP404；metadata確認模型存在，現已分類provider_unavailable而非永久block。摘要模型保持3.5，搜尋為使用者同意的2.5；待取得固定公開probe的遮罩錯誤訊息。新增僅限固定公開prompt的trace診斷，32項相關測試/Ruff通過，不能用於私人prompt。

確切根因：遮罩probe run40321203612/job121566287368，Google回覆This model models/gemini-2.5-flash-lite is no longer available to new users，建議3.5與Interactions API。並非catalog缺失，也不是一次暫時404。使用者同意的免費替代方案對目前API專案不可用，不能宣稱已修好。
新增對明確新使用者不可用回覆的配置封鎖，避免metadata200造成無限退避重試；保留未知404的查核與退避。準備回復原3.5搜尋設定，摘要維持3.5，pending不丟棄。不開billing、不換未授權第三模型、不關grounding。新測試確認一次失敗後不再發請求。

## 本輪最終可驗證狀態
更新：2026-10-26（Asia/Taipei）。
- 已回復並讀回GEMINI_SEARCH_MODEL=gemini-3.5-flash-lite；影片摘要亦維持原3.5。未啟用billing、未授權第三模型。
- 根因證據run40321203612：2.5Flash-Lite在catalog存在，但Google明確拒絕新使用者生成；同意的免費方案未成功，不能稱部署成功或YT已恢復。
- 修正commit615e0c2已推送；369項全套離線測試通過（5.05s）、Ruff通過；GitHub CI40321644594成功。
- 原owner/Bankless修復仍保留，常駐服務不需為本次YT設定另重啟。pending影片未刪除或假標完成。新policy在下次YT workflow讀取新程式；本輪沒有為已知不支援免費grounding的原3.5再次浪費請求。
- 尚未完成：真實YouTube查證與完整送達。進一步路徑需要使用者同意並親自啟用Google付費帳務，或另明確授權其他模型/查證方案；不能把一次失敗設定變更當成功完成。
- 診斷workflow為手動唯讀、無狀態共寫；probe_search使用YT原workflow單一writer與日配額，沒有繞過錯誤/配額保護。
commit/push：本紀錄另提交，任務等待上述必要使用者決策，不標記為全部修復。
