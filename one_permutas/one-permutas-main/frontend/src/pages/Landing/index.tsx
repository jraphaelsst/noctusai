import { useEffect, useState } from 'react'

const Landing = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    localStorage.getItem('authTokens')
      ? setIsAuthenticated(true)
      : setIsAuthenticated(false)
  }, [])

  return (
    <div>
      {isAuthenticated ? (
        <span>Você está autenticado!</span>
      ) : (
        <span>Você não está autenticado, faça login</span>
      )}
    </div>
  )
}

export default Landing
