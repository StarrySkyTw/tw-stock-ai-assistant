import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "台股 AI 投資決策助手",
  description: "台股技術、籌碼、基本面、風險與 AI 新聞摘要儀表板"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}

