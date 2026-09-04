import { useContext, useMemo, useRef, useEffect } from 'react'

import axios from 'axios'
import dayjs from 'dayjs'

import AuthContext from '../context/AuthContext'

import { jwtDecode } from 'jwt-decode'

const baseURL = '/api'

const useAxios = () => {
  const { authTokens, setAuthTokens, setUser } = useContext(AuthContext)
  const authTokensRef = useRef(authTokens)
  const setAuthTokensRef = useRef(setAuthTokens)
  const setUserRef = useRef(setUser)

  useEffect(() => {
    authTokensRef.current = authTokens
    setAuthTokensRef.current = setAuthTokens
    setUserRef.current = setUser
  }, [authTokens, setAuthTokens, setUser])

  const axiosInstance = useMemo(() => {
    const instance = axios.create({
      baseURL,
      headers: { Authorization: `Bearer ${authTokens?.access}` }
    })

    instance.interceptors.request.use(async (req) => {
      const tokens = authTokensRef.current
      if (!tokens?.access) {
        return req
      }

      const user = jwtDecode(tokens.access)
      const isExpired = dayjs.unix(user.exp).diff(dayjs()) < 1

      if (!isExpired) {
        req.headers.Authorization = `Bearer ${tokens.access}`
        return req
      }

      try {
        const response = await axios.post(`${baseURL}/token/refresh/`, {
          refresh: tokens.refresh
        })

        localStorage.setItem('authTokens', JSON.stringify(response.data))

        setAuthTokensRef.current(response.data)
        setUserRef.current(jwtDecode(response.data.access))

        req.headers.Authorization = `Bearer ${response.data.access}`
      } catch (error) {
        console.error('Token refresh failed:', error)
      }

      return req
    })

    return instance
  }, [])

  return axiosInstance
}

export default useAxios
