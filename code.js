// code.js — الخيط الرئيسي لـ Figma Plugin
// يستقبل بيانات المحاكاة من ui.html ويرسمها كرسم بياني حقيقي على الكانفس

figma.showUI(__html__, { width: 320, height: 480 });

const CHART_WIDTH = 700;
const CHART_HEIGHT = 350;
const PADDING = 40;

figma.ui.onmessage = async (msg) => {
  if (msg.type !== "draw-chart") return;

  const data = msg.data;
  await drawChart(data);
};

async function drawChart(data) {
  const series = data.series; // [{date, baseline_balance, scenario_balance}, ...]

  // إطار رئيسي يحتوي كل شيء
  const frame = figma.createFrame();
  frame.name = `محاكاة: ${data.decision_description}`;
  frame.resize(CHART_WIDTH + PADDING * 2, CHART_HEIGHT + PADDING * 2 + 80);
  frame.fills = [{ type: "SOLID", color: { r: 0.117, g: 0.117, b: 0.117 } }];

  // ---- تحديد نطاق القيم لرسم المحاور ----
  const allValues = series.flatMap(p => [p.baseline_balance, p.scenario_balance]);
  const minVal = Math.min(...allValues, data.safe_minimum_balance);
  const maxVal = Math.max(...allValues);
  const range = maxVal - minVal || 1;

  const xStep = CHART_WIDTH / (series.length - 1);
  const yFor = (val) => PADDING + CHART_HEIGHT - ((val - minVal) / range) * CHART_HEIGHT;

  // ---- خط الحد الآمن (Safe Minimum) ----
  const safeY = yFor(data.safe_minimum_balance);
  const safeLine = figma.createVector();
  safeLine.name = "الحد الآمن";
  safeLine.vectorPaths = [{
    windingRule: "NONE",
    data: `M ${PADDING} ${safeY} L ${PADDING + CHART_WIDTH} ${safeY}`,
  }];
  safeLine.strokes = [{ type: "SOLID", color: { r: 0.765, g: 0.42, b: 0.306 } }];
  safeLine.strokeWeight = 1.5;
  safeLine.dashPattern = [6, 4];
  frame.appendChild(safeLine);

  // ---- خط Baseline (بدون قرار) ----
  frame.appendChild(buildLine(series, "baseline_balance", yFor, xStep,
    { r: 0.557, g: 0.486, b: 0.765 }, "Baseline (بدون قرار)"));

  // ---- خط Scenario (مع القرار) ----
  frame.appendChild(buildLine(series, "scenario_balance", yFor, xStep,
    { r: 0.906, g: 0.298, b: 0.235 }, `السيناريو: ${data.decision_description}`));

  // ---- نقطة خطر التعثر (إن وجدت) ----
  if (data.risk.scenario_risk_date) {
    const riskIndex = series.findIndex(p => p.date === data.risk.scenario_risk_date);
    if (riskIndex >= 0) {
      const dot = figma.createEllipse();
      dot.resize(10, 10);
      dot.fills = [{ type: "SOLID", color: { r: 1, g: 0, b: 0 } }];
      dot.name = "نقطة خطر التعثر";
      frame.appendChild(dot); // نلحقه بالإطار أولاً حتى تكون الإحداثيات نسبية له
      dot.x = PADDING + riskIndex * xStep - 5;
      dot.y = yFor(series[riskIndex].scenario_balance) - 5;
    }
  }

  // ---- نص ملخص أعلى الرسم ----
  await figma.loadFontAsync({ family: "Inter", style: "Regular" });
  await figma.loadFontAsync({ family: "Inter", style: "Bold" });

  const title = figma.createText();
  title.fontName = { family: "Inter", style: "Bold" };
  title.fontSize = 16;
  title.characters = `القرار: ${data.decision_description}`;
  title.x = PADDING;
  title.y = 10;
  title.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
  frame.appendChild(title);

  const summary = figma.createText();
  summary.fontName = { family: "Inter", style: "Regular" };
  summary.fontSize = 12;
  summary.x = PADDING;
  summary.y = PADDING + CHART_HEIGHT + 45;
  const isSafe = data.risk.is_safe;
  summary.characters = isSafe
    ? `آمن ماليًا لمدة ${data.forecast_months} شهر بعد هذا القرار.`
    : `تحذير: الرصيد سينخفض تحت الحد الآمن بتاريخ ${data.risk.scenario_risk_date} (عجز متوقع: ${data.risk.deficit_amount} ريال).`;
  summary.fills = [{
    type: "SOLID",
    color: isSafe ? { r: 0.3, g: 0.8, b: 0.4 } : { r: 0.9, g: 0.3, b: 0.3 },
  }];
  frame.appendChild(summary);

  figma.viewport.scrollAndZoomIntoView([frame]);
  figma.currentPage.selection = [frame];
  figma.notify("تم رسم المحاكاة ✅");
}

function buildLine(series, key, yFor, xStep, color, name) {
  const line = figma.createVector();
  line.name = name;
  let path = `M ${PADDING} ${yFor(series[0][key])} `;
  for (let i = 1; i < series.length; i++) {
    path += `L ${PADDING + i * xStep} ${yFor(series[i][key])} `;
  }
  line.vectorPaths = [{ windingRule: "NONE", data: path.trim() }];
  line.strokes = [{ type: "SOLID", color }];
  line.strokeWeight = 2.5;
  return line;
}
