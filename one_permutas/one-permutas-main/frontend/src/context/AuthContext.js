import { createContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { jwtDecode } from 'jwt-decode'

import swal from 'sweetalert2'

const AuthContext = createContext()
export default AuthContext

export const AuthProvider = ({ children }) => {
  const [authTokens, setAuthTokens] = useState(() =>
    localStorage.getItem('authTokens')
      ? JSON.parse(localStorage.getItem('authTokens'))
      : null
  )

  const [user, setUser] = useState(() =>
    localStorage.getItem('authTokens')
      ? jwtDecode(localStorage.getItem('authTokens'))
      : null
  )

  const [loading, setLoading] = useState(true)

  const navigate = useNavigate()

  const loginUser = async (email, password) => {
    const response = await fetch('http://localhost:8000/token/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ email, password })
    })

    const data = await response.json()

    if (response.status === 200) {
      setAuthTokens(data)
      setUser(jwtDecode(data.access))

      localStorage.setItem('authTokens', JSON.stringify(data))

      navigate('/home')
      console.log(user)

      swal.fire({
        title: 'Login Successful',
        icon: 'success',
        toast: true,
        timer: 6000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButtom: false
      })
    } else {
      swal.fire({
        title: 'Username or password does not exist.',
        icon: 'error',
        toast: true,
        timer: 6000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButtom: false
      })
    }
  }

  const registerUser = async (username, email, password, password2) => {
    const response = await fetch('http://localhost:8000/register/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        username,
        email,
        password,
        password2
      })
    })

    if (response.status === 201) {
      navigate('/login')

      swal.fire({
        title: 'User created successfuly.',
        icon: 'success',
        toast: true,
        timer: 6000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })
    } else {
      swal.fire({
        title: 'An error occurred.',
        icon: 'error',
        toast: true,
        timer: 6000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButtom: false
      })
    }
  }

  const logoutUser = () => {
    setAuthTokens(null)
    setUser(null)

    localStorage.removeItem('authTokens')

    navigate('/login')
  }

  const contextData = {
    user,
    setUser,
    authTokens,
    setAuthTokens,
    registerUser,
    loginUser,
    logoutUser
  }

  useEffect(() => {
    if (authTokens) {
      setUser(jwtDecode(authTokens.access))
    }
    setLoading(false)
  }, [authTokens, loading])

  return (
    <AuthContext.Provider value={contextData}>
      {loading ? null : children}
    </AuthContext.Provider>
  )
}
