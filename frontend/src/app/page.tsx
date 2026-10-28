type Product = {
  id: string;
  name: string;
  image_url: string;
  created_at: string;
};

async function getProducts(): Promise<Product[]> {
  const apiUrl =
    process.env.CATALOG_API_URL ?? "http://localhost:8000/api/products";

  const response = await fetch(apiUrl, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Catalog API returned ${response.status}`);
  }

  return response.json();
}

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let products: Product[] = [];
  let hasError = false;

  try {
    products = await getProducts();
  } catch {
    hasError = true;
  }

  return (
    <main className="page">
      <h1>Каталог</h1>

      {hasError ? (
        <p>Не удалось загрузить товары. Попробуйте обновить страницу.</p>
      ) : products.length === 0 ? (
        <p>Пока товаров нет.</p>
      ) : (
        <ul className="products">
          {products.map((product) => (
            <li className="product" key={product.id}>
              <img src={product.image_url} alt={product.name} />
              <h2>{product.name}</h2>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
