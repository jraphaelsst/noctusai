import { Provider } from 'react-redux'
import { BrowserRouter as Router } from 'react-router-dom'

import { GlobalCss } from './styles'
import { store } from './store'

import { AuthProvider } from './context/AuthContext'
import Rotas from './routes'

function App() {
  return (
    <Provider store={store}>
      <Router>
        <AuthProvider>
          <GlobalCss />
          <Rotas />
        </AuthProvider>
      </Router>
    </Provider>
  )
}

export default App
