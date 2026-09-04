import { Outlet } from 'react-router-dom'
import Navbar from '../components/Navbar'

const AuthenticatedLayout = () => {
  return (
    <Navbar>
      <Outlet />
    </Navbar>
  )
}

export default AuthenticatedLayout
