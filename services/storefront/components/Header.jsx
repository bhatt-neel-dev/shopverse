import Link from "next/link";
import SearchBox from "./SearchBox";

export default function Header() {
  return (
    <header className="site-header">
      <div className="container header-row">
        <Link href="/" className="brand">
          Shop<span>Verse</span>
        </Link>
        <SearchBox />
        <nav className="nav">
          <Link href="/">Products</Link>
          <Link href="/cart">Cart</Link>
          <Link href="/checkout">Checkout</Link>
        </nav>
      </div>
    </header>
  );
}
