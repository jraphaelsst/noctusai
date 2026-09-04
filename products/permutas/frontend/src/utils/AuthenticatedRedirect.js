import { useContext } from 'react'
import { Navigate } from 'react-router-dom'

import AuthContext from '../context/AuthContext'

const AuthenticatedRedirect = ({ children }) => {
  let { user } = useContext(AuthContext)
  return user ? <Navigate to="/home" /> : children
}

export default AuthenticatedRedirect
