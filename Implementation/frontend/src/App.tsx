import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import TableDetail from './pages/TableDetail'
import Scraper from './pages/Scraper'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/table/:tableName" element={<TableDetail />} />
        <Route path="/scraper" element={<Scraper />} />
      </Routes>
    </Layout>
  )
}

export default App

