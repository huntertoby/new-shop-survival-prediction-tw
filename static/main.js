// static/main.js
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("search-form");

  const addressInput = document.getElementById("address");
  const totalAssetInput = document.getElementById("total_asset");
  const industrySelect = document.getElementById("industry");
  const modelYearSelect = document.getElementById("model_year");

  const errorBox = document.getElementById("error-box");
  const infoBox = document.getElementById("info-box");

  const predictSection = document.getElementById("predict-section");
  const predictResult = document.getElementById("predict-result");

  const loadingOverlay = document.getElementById("loading-overlay");

  function setLoading(isLoading) {
    if (!loadingOverlay) return;
    loadingOverlay.style.display = isLoading ? "flex" : "none";
  }

  function showError(msg) {
    errorBox.style.display = "block";
    errorBox.textContent = msg;
  }

  function clearError() {
    errorBox.style.display = "none";
    errorBox.textContent = "";
  }

  function clearResults() {
    infoBox.style.display = "none";
    infoBox.innerHTML = "";

    predictSection.style.display = "none";
    predictResult.innerHTML = "";
  }

  function renderResult(data) {
    clearResults();

    const geo = data.geocode;

    infoBox.style.display = "block";

    const cityText = geo.city || "未知";
    const districtText = geo.district || "未知";

    infoBox.innerHTML = `
      <div>原始輸入地址：${data.address_input}</div>
      <div>比對地址：${geo.match_addr}（score: ${geo.score}）</div>
      <div>推測縣市：${cityText}</div>
      <div>行政區：${districtText}</div>
      <div>座標：lat = ${geo.lat}, lng = ${geo.lng}</div>
      <div>搜尋半徑：${data.radius_m} 公尺</div>
    `;

    if (data.survival) {
      const s = data.survival;
      predictSection.style.display = "block";

      const probPercent = (s.prob * 100).toFixed(2);
      const thresholdPercent = (s.threshold * 100).toFixed(2);
      const year = s.year || modelYearSelect.value;

      predictResult.innerHTML = `
        <div>預測期間：<strong>${year} 年</strong></div>
        <div>預測存活機率：<strong>${probPercent}%</strong></div>
        <div>決策門檻：${thresholdPercent}%</div>
        <div>判定結果：${s.label}</div>
      `;
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();
    clearResults();

    const address = addressInput.value.trim();
    const totalAsset = totalAssetInput.value.trim();
    const industry = industrySelect.value;
    const modelYear = modelYearSelect.value;

    if (!address) {
      showError("請先輸入地址。");
      return;
    }
    if (!totalAsset) {
      showError("請輸入總資產。");
      return;
    }
    if (!industry) {
      showError("請選擇行業別。");
      return;
    }

    try {
      setLoading(true);  // 顯示轉圈圈

      const resp = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: address,
          total_asset: totalAsset,
          industry: industry,
          model_year: modelYear,
          // 不再傳 radius_m，後端會用預設 500
        }),
      });

      const data = await resp.json();

      if (!data.ok) {
        showError(data.error || "查詢失敗。");
        return;
      }

      renderResult(data);
    } catch (err) {
      console.error(err);
      showError("無法連線到伺服器，請稍後再試。");
    } finally {
      setLoading(false); // 關閉轉圈圈
    }
  });
});
