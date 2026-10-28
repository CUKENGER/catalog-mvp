import type { Metadata } from "next";
import "./globals.css";
import { TelegramInit } from "./telegram-init";

export const metadata: Metadata = {
  title: "Каталог",
  description: "Каталог товаров",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>
        <TelegramInit />
        {children}
      </body>
    </html>
  );
}
