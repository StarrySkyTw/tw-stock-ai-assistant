export const STOCK_NAME_FALLBACKS: Record<string, string> = {
  "0050": "元大台灣50",
  "0056": "元大高股息",
  "00878": "國泰永續高股息",
  "1101": "台泥",
  "1216": "統一",
  "1303": "南亞",
  "2002": "中鋼",
  "2308": "台達電",
  "2313": "華通",
  "2317": "鴻海",
  "2330": "台積電",
  "2357": "華碩",
  "2379": "瑞昱",
  "2382": "廣達",
  "2412": "中華電",
  "2449": "京元電子",
  "2454": "聯發科",
  "2603": "長榮",
  "2609": "陽明",
  "2615": "萬海",
  "2881": "富邦金",
  "2882": "國泰金",
  "2891": "中信金",
  "3008": "大立光",
  "3034": "聯詠",
  "3231": "緯創",
  "3443": "創意",
  "3653": "健策",
  "3661": "世芯-KY",
  "3665": "貿聯-KY",
  "3693": "營邦",
  "3706": "神達",
  "3711": "日月光投控",
  "5871": "中租-KY",
  "6285": "啟碁",
  "6451": "訊芯-KY"
};

const UNKNOWN_STOCK_LABEL = "待確認代碼";

const PLACEHOLDER_NAMES = new Set(["自訂觀察", "資料同步中", "產業資料待補", UNKNOWN_STOCK_LABEL]);

const INDUSTRY_LABELS = new Set([
  "其他產業",
  "台股大型權值 ETF",
  "台股高股息 ETF",
  "台股 ESG 高股息 ETF",
  "半導體晶圓代工",
  "電子代工與 AI 伺服器",
  "IC 設計",
  "AI 伺服器與電子代工",
  "電源管理與工業自動化",
  "半導體封測控股",
  "半導體封測",
  "半導體測試服務",
  "半導體",
  "電腦及週邊設備",
  "電信服務",
  "航運",
  "金融控股",
  "光學鏡頭",
  "高速傳輸與網通晶片",
  "ASIC 與 AI 晶片",
  "半導體 IP",
  "品牌電腦與伺服器",
  "IC 設計與高速傳輸",
  "AI 伺服器與雲端設備",
  "租賃金融",
  "食品與內需",
  "塑化",
  "鋼鐵",
  "水泥",
  "電子零組件",
  "其他電子",
  "通信網路",
  "光電",
  "化工",
  "電機機械",
  "生技醫療"
]);

export function knownStockName(symbol: string) {
  return STOCK_NAME_FALLBACKS[normalizeStockSymbol(symbol)] ?? null;
}

export function normalizeStockName(symbol: string, name: string | null | undefined) {
  const normalizedSymbol = normalizeStockSymbol(symbol);
  const cleaned = String(name ?? "").trim();
  if (!cleaned || cleaned === normalizedSymbol || PLACEHOLDER_NAMES.has(cleaned) || INDUSTRY_LABELS.has(cleaned)) {
    return knownStockName(normalizedSymbol) ?? UNKNOWN_STOCK_LABEL;
  }
  return cleaned;
}

export function displayStockName(symbol: string, name: string | null | undefined) {
  return normalizeStockName(symbol, name);
}

function normalizeStockSymbol(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9.^-]/g, "").trim();
}
