import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, getToken, money, productImage, setToken } from './api'
import Ops from './Ops'

const ShopContext = createContext(null)
export const useShop = () => useContext(ShopContext)

function ShopProvider({ children }) {
  const [user, setUser] = useState(null)
  const [cartCount, setCartCount] = useState(0)

  async function refresh() {
    if (!getToken()) {
      setUser(null)
      setCartCount(0)
      return
    }
    try {
      const me = await api('/auth/me')
      const cart = await api('/cart')
      setUser(me)
      setCartCount(cart.items.reduce((sum, item) => sum + item.quantity, 0))
    } catch {
      setToken('')
      setUser(null)
      setCartCount(0)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const value = useMemo(() => ({ user, cartCount, refresh, setUser }), [user, cartCount])
  return <ShopContext.Provider value={value}>{children}</ShopContext.Provider>
}

function Layout() {
  const { user, cartCount } = useShop()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">Northline</Link>
        <nav className="nav">
          <NavLink to="/products">Shop</NavLink>
          <NavLink to="/wishlist">Wishlist</NavLink>
          <NavLink to="/orders">Orders</NavLink>
        </nav>
        <form className="top-search" onSubmit={(event) => { event.preventDefault(); navigate(`/products?q=${encodeURIComponent(q)}`) }}>
          <input aria-label="Search products" placeholder="Search the shop" value={q} onChange={(event) => setQ(event.target.value)} />
        </form>
        <div className="top-actions">
          {user ? <Link to="/profile">{user.full_name.split(' ')[0]}</Link> : <Link to="/login">Sign in</Link>}
          <Link className="cart-link" to="/cart">Cart ({cartCount})</Link>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/products" element={<Catalog />} />
        <Route path="/products/:slug" element={<Product />} />
        <Route path="/cart" element={<Cart />} />
        <Route path="/wishlist" element={<Wishlist />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/:id" element={<OrderDetail />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    </div>
  )
}

function ProductCard({ product }) {
  return (
    <article className="card">
      <Link to={`/products/${product.slug}`}>
        <img src={productImage(product.image_file)} alt="" />
        <div className="card-body">
          <div className="muted">{product.category_name}</div>
          <strong>{product.name}</strong>
          <div className="spread">
            <span className="price">{money(product.price_cents)}</span>
            <span className="muted">{product.stock > 0 ? `${product.stock} in stock` : 'Sold out'}</span>
          </div>
        </div>
      </Link>
    </article>
  )
}

function Home() {
  const [items, setItems] = useState([])
  useEffect(() => { api('/products?limit=4&sort=newest').then((page) => setItems(page.items)) }, [])
  return (
    <>
      <section className="hero">
        <div>
          <p className="muted">Household goods, chosen slowly</p>
          <h1>Objects for the table, the desk, and the road.</h1>
          <p className="lede">Northline is a customer shop with real stock, checkout, and order tracking. Browse the catalogue, keep a wishlist, and pay with the simulated card gateway.</p>
          <Link className="btn" to="/products">Browse the shop</Link>
        </div>
        <div className="hero-panel">
          <div>
            <div className="muted">Free shipping</div>
            <strong>Orders from $75 travel free.</strong>
          </div>
          <p>A sample customer is ready in the sign-in form if you want to skip registration.</p>
        </div>
      </section>
      <section className="section">
        <div className="section-title"><h2>Just in</h2><Link to="/products">View all</Link></div>
        <div className="grid">{items.map((product) => <ProductCard key={product.id} product={product} />)}</div>
      </section>
    </>
  )
}

function Catalog() {
  const [params, setParams] = useSearchParams()
  const [page, setPage] = useState({ items: [], total: 0 })
  const [categories, setCategories] = useState([])
  const q = params.get('q') || ''
  const category = params.get('category') || ''
  const sort = params.get('sort') || 'newest'
  const inStock = params.get('in_stock') || ''

  useEffect(() => { api('/categories').then(setCategories) }, [])
  useEffect(() => {
    const query = new URLSearchParams()
    if (q) query.set('q', q)
    if (category) query.set('category', category)
    if (sort) query.set('sort', sort)
    if (inStock) query.set('in_stock', inStock)
    api(`/products?${query.toString()}`).then(setPage)
  }, [q, category, sort, inStock])

  function update(next) {
    const merged = { q, category, sort, in_stock: inStock, ...next }
    Object.keys(merged).forEach((key) => { if (!merged[key]) delete merged[key] })
    setParams(merged)
  }

  return (
    <>
      <div className="page-head">
        <h1>The shop</h1>
        <p className="muted">{page.total} pieces</p>
        <div className="filters">
          <input aria-label="Filter by words" value={q} placeholder="Search" onChange={(event) => update({ q: event.target.value })} />
          <select aria-label="Category" value={category} onChange={(event) => update({ category: event.target.value })}>
            <option value="">All rooms</option>
            {categories.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}
          </select>
          <select aria-label="Stock" value={inStock} onChange={(event) => update({ in_stock: event.target.value })}>
            <option value="">Any stock</option>
            <option value="true">In stock</option>
            <option value="false">Sold out</option>
          </select>
          <select aria-label="Sort" value={sort} onChange={(event) => update({ sort: event.target.value })}>
            <option value="newest">Newest</option>
            <option value="price_asc">Price, low</option>
            <option value="price_desc">Price, high</option>
            <option value="name">Name</option>
          </select>
        </div>
      </div>
      <section className="section">
        <div className="catalog-grid">{page.items.map((product) => <ProductCard key={product.id} product={product} />)}</div>
      </section>
    </>
  )
}

function Product() {
  const { slug } = useParams()
  const { user, refresh } = useShop()
  const [product, setProduct] = useState(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  useEffect(() => { api(`/products/${slug}`).then(setProduct).catch((err) => setError(err.message)) }, [slug])
  if (error) return <div className="section error">{error}</div>
  if (!product) return <div className="section">Loading…</div>

  async function add(path, body) {
    setError('')
    setNote('')
    if (!user) {
      setError('Sign in to keep a cart or wishlist.')
      return
    }
    try {
      await api(path, { method: 'POST', body })
      await refresh()
      setNote(path.includes('wishlist') ? 'Saved to your wishlist.' : 'Added to your cart.')
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="split">
      <div className="product-photo card"><img src={productImage(product.image_file)} alt={product.name} /></div>
      <div className="product-copy">
        <div className="muted">{product.category_name} · {product.sku}</div>
        <h1>{product.name}</h1>
        <p>{product.description}</p>
        <p className="price">{money(product.price_cents)}</p>
        <p className="muted">{product.stock > 0 ? `${product.stock} available` : 'Sold out'}</p>
        {error && <div className="error">{error}</div>}
        {note && <div className="notice">{note}</div>}
        <div className="row">
          <button className="btn" disabled={product.stock < 1} onClick={() => add('/cart/items', { product_id: product.id, quantity: 1 })}>Add to cart</button>
          <button className="btn-line" onClick={() => add(`/wishlist/${product.id}`)}>Save</button>
        </div>
      </div>
    </div>
  )
}

function Cart() {
  const { refresh } = useShop()
  const [cart, setCart] = useState(null)
  const [error, setError] = useState('')
  async function load() {
    const next = await api('/cart')
    setCart(next)
    refresh()
  }
  useEffect(() => { load().catch((err) => setError(err.message)) }, [])
  if (error) return <div className="section error">{error}</div>
  if (!cart) return <div className="section">Loading…</div>
  return (
    <section className="section">
      <h1>Cart</h1>
      {cart.items.length === 0 && <p>Your cart is empty.</p>}
      {cart.items.map((item) => (
        <div className="spread card pad" key={item.id} style={{ marginBottom: 12 }}>
          <div className="row">
            <img src={productImage(item.image_file)} alt="" width="72" height="72" />
            <div>
              <strong>{item.name}</strong>
              <div className="muted">{money(item.unit_price_cents)}</div>
            </div>
          </div>
          <div className="row">
            <input aria-label={`Quantity for ${item.name}`} style={{ width: 70 }} type="number" min="1" max="10" defaultValue={item.quantity} onBlur={(event) => api(`/cart/items/${item.id}`, { method: 'PATCH', body: { quantity: Number(event.target.value) } }).then(load).catch((err) => setError(err.message))} />
            <button className="btn-line" onClick={() => api(`/cart/items/${item.id}`, { method: 'DELETE' }).then(load)}>Remove</button>
            <strong>{money(item.line_total_cents)}</strong>
          </div>
        </div>
      ))}
      <div className="totals">
        <div className="spread"><span>Subtotal</span><span>{money(cart.subtotal_cents)}</span></div>
        <div className="spread"><span>Shipping</span><span>{money(cart.shipping_cents)}</span></div>
        <div className="spread"><strong>Total</strong><strong>{money(cart.total_cents)}</strong></div>
        <Link className="btn" to="/checkout">Checkout</Link>
      </div>
    </section>
  )
}

function Wishlist() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api('/wishlist').then(setItems).catch((err) => setError(err.message)) }, [])
  if (error) return <div className="section error">{error}</div>
  if (!items) return <div className="section">Loading…</div>
  return (
    <section className="section">
      <h1>Wishlist</h1>
      {items.length === 0 && <p>Nothing saved yet.</p>}
      <div className="grid">{items.map((product) => <ProductCard key={product.id} product={product} />)}</div>
    </section>
  )
}

function Checkout() {
  const { user, refresh } = useShop()
  const navigate = useNavigate()
  const [cart, setCart] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState(null)
  useEffect(() => {
    if (!user) return
    setForm({
      full_name: user.full_name,
      address_line: user.address_line,
      city: user.city,
      postal_code: user.postal_code,
      country: user.country,
      cardholder_name: user.full_name,
      card_number: '4242424242424242',
      expiry_month: 12,
      expiry_year: 2030,
      cvc: '123',
    })
    api('/cart').then(setCart).catch((err) => setError(err.message))
  }, [user])
  if (!user) return <div className="section">Sign in before checkout.</div>
  if (!form || !cart) return <div className="section">Loading…</div>

  function set(key, value) { setForm({ ...form, [key]: value }) }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const order = await api('/checkout', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID().replaceAll('-', '') },
        body: {
          full_name: form.full_name,
          address_line: form.address_line,
          city: form.city,
          postal_code: form.postal_code,
          country: form.country,
          card: {
            cardholder_name: form.cardholder_name,
            card_number: form.card_number,
            expiry_month: Number(form.expiry_month),
            expiry_year: Number(form.expiry_year),
            cvc: form.cvc,
          },
        },
      })
      await refresh()
      navigate(`/orders/${order.id}`)
    } catch (err) {
      setError(err.message)
      const orderId = err.data?.detail?.order_id
      if (orderId) navigate(`/orders/${orderId}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="section">
      <h1>Checkout</h1>
      <p className="muted">Total {money(cart.total_cents)}. Use 4242 4242 4242 4242 to approve, 4000 0000 0000 0002 to decline, or 4000 0000 0000 9995 to time out.</p>
      {error && <div className="error">{error}</div>}
      <form className="form" onSubmit={submit}>
        {['full_name', 'address_line', 'city', 'postal_code', 'country', 'cardholder_name', 'card_number', 'expiry_month', 'expiry_year', 'cvc'].map((key) => (
          <label className="field" key={key}>
            <span>{key.replaceAll('_', ' ')}</span>
            <input value={form[key]} onChange={(event) => set(key, event.target.value)} required />
          </label>
        ))}
        <button className="btn clay" disabled={busy || cart.items.length === 0}>{busy ? 'Placing order…' : 'Place order'}</button>
      </form>
    </section>
  )
}

function Orders() {
  const [orders, setOrders] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api('/orders').then(setOrders).catch((err) => setError(err.message)) }, [])
  if (error) return <div className="section error">{error}</div>
  if (!orders) return <div className="section">Loading…</div>
  return (
    <section className="section">
      <h1>Orders</h1>
      {orders.length === 0 && <p>You have not placed an order yet.</p>}
      {orders.map((order) => (
        <Link key={order.id} to={`/orders/${order.id}`} className="spread card pad" style={{ marginBottom: 12 }}>
          <div>
            <strong>{order.order_number}</strong>
            <div className="muted">{order.status} · payment {order.payment_status}</div>
          </div>
          <span>{money(order.total_cents)}</span>
        </Link>
      ))}
    </section>
  )
}

function OrderDetail() {
  const { id } = useParams()
  const [order, setOrder] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api(`/orders/${id}`).then(setOrder).catch((err) => setError(err.message)) }, [id])
  if (error) return <div className="section error">{error}</div>
  if (!order) return <div className="section">Loading…</div>
  return (
    <section className="section">
      <h1>{order.order_number}</h1>
      <p className="muted">{order.status} · card ending {order.card_last4} · {money(order.total_cents)}</p>
      <p>{order.full_name}, {order.address_line}, {order.city} {order.postal_code}, {order.country}</p>
      {order.items.map((item) => (
        <div key={item.sku} className="spread"><span>{item.quantity} × {item.name}</span><span>{money(item.unit_price_cents * item.quantity)}</span></div>
      ))}
      <h2>Tracking</h2>
      <ul className="timeline">
        {order.tracking.map((event) => (
          <li key={`${event.status}-${event.created_at}`}>
            <strong>{event.message}</strong>
            <div className="muted">{new Date(event.created_at).toLocaleString()}</div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Profile() {
  const { user, refresh } = useShop()
  const [form, setForm] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { if (user) setForm(user) }, [user])
  if (!user || !form) return <div className="section">Sign in to edit your profile.</div>
  async function save(event) {
    event.preventDefault()
    setError('')
    try {
      await api('/profile', { method: 'PATCH', body: form })
      await refresh()
      setMessage('Profile saved.')
    } catch (err) {
      setError(err.message)
    }
  }
  return (
    <section className="section">
      <h1>Profile</h1>
      {message && <div className="notice">{message}</div>}
      {error && <div className="error">{error}</div>}
      <form className="form" onSubmit={save}>
        {['full_name', 'phone', 'address_line', 'city', 'postal_code', 'country'].map((key) => (
          <label className="field" key={key}><span>{key.replaceAll('_', ' ')}</span>
            <input value={form[key] || ''} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
          </label>
        ))}
        <button className="btn">Save profile</button>
      </form>
      <p className="muted">{user.email}</p>
    </section>
  )
}

function AuthForm({ mode }) {
  const navigate = useNavigate()
  const { refresh } = useShop()
  const [error, setError] = useState('')
  const [form, setForm] = useState({ email: 'demo@northline.shop', password: 'DemoPass123!', full_name: '' })
  async function submit(event) {
    event.preventDefault()
    setError('')
    try {
      const path = mode === 'login' ? '/auth/login' : '/auth/register'
      const body = mode === 'login' ? { email: form.email, password: form.password } : form
      const result = await api(path, { method: 'POST', body })
      setToken(result.access_token)
      await refresh()
      navigate('/')
    } catch (err) {
      setError(err.message)
    }
  }
  return (
    <section className="section">
      <h1>{mode === 'login' ? 'Sign in' : 'Create an account'}</h1>
      {mode === 'login' && <p className="muted">Sample customer: demo@northline.shop / DemoPass123!</p>}
      {error && <div className="error">{error}</div>}
      <form className="form" onSubmit={submit}>
        {mode === 'register' && <label className="field"><span>Full name</span><input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required /></label>}
        <label className="field"><span>Email</span><input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label>
        <label className="field"><span>Password</span><input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required /></label>
        <button className="btn">{mode === 'login' ? 'Sign in' : 'Register'}</button>
      </form>
      {mode === 'login' ? <Link to="/register">Create an account</Link> : <Link to="/login">Already registered?</Link>}
    </section>
  )
}
const Login = () => <AuthForm mode="login" />
const Register = () => <AuthForm mode="register" />

export default function App() {
  return (
    <ShopProvider>
      <Routes>
        <Route path="/ops" element={<Ops />} />
        <Route path="/*" element={<Layout />} />
      </Routes>
    </ShopProvider>
  )
}
