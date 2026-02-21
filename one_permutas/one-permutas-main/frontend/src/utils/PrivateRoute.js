import { useContext } from 'react'
import { Navigate } from 'react-router-dom'

import AuthContext from '../context/AuthContext'
import Navbar from '../components/Navbar'

const PrivateRoute = ({ children }) => {
  let { user } = useContext(AuthContext)
  return !user ? <Navigate to="/login" /> : <Navbar>{children}</Navbar>
}

export default PrivateRoute
