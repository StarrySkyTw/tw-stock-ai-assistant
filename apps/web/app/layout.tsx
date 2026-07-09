import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "台股研究判斷小幫手",
  description: "以研究結論、門檻檢查、觀察清單與決策紀錄協助判斷台股。"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
