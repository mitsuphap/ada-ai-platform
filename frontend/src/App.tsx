import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import TableDetail from './pages/TableDetail'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/table/:tableName" element={<TableDetail />} />
      </Routes>
    </Layout>
  )
}

export default App

