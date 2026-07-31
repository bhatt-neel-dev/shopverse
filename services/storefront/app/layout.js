import "./globals.css";
import Header from "../components/Header";

export const metadata = {
  title: "ShopVerse",
  description: "ShopVerse demo storefront — the observable fake shop.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        {/* ==================================================================
            MOTADATA RUM SDK — PLACEHOLDER (do not remove)

            The Motadata Real User Monitoring browser snippet will be pasted
            here (or moved into a <Script strategy="beforeInteractive"> tag)
            once the RUM application is registered in Motadata and the SDK
            snippet + application key are issued. Until then this block is
            intentionally empty — do NOT fabricate SDK code.
           ================================================================== */}
        <Header />
        <div className="page">{children}</div>
        <footer className="site-footer">
          <div className="container">
            ShopVerse — a synthetic storefront for the Motadata observability
            demo. Every request carries an <code>X-Trace-Id</code>.
          </div>
        </footer>
      </body>
    </html>
  );
}
