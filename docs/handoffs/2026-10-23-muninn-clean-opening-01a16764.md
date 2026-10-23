# Munnin 移除開場標題與箭頭

更新：2026-10-23（Asia/Taipei）；基準 main / 153a8f1，hook 已確認同步。
範圍：yt_monitor 提示詞及 renderer、相關測試與雙語 README。
已實作：開場直接呈現結論，不顯示「重點」；renderer 也移除尚未組裝的舊摘要獨立「重點」行，保留內文與「解決什麼問題」。觀看原片連結移除箭頭符號。
不重寫已保存 delivery parts，不影響既有分段續送；其他本機配額修改保留。
已驗證：45 項相關離線測試、focused Ruff 與 git diff --check 通過。
提交推送：本次六個檔案作單一 atomic commit；結果以本次最終回覆為準。未新增模型請求或群組預覽。
