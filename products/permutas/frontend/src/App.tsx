import { Provider } from 'react-redux'
import { BrowserRouter as Router } from 'react-router-dom'

import { GlobalCss } from './styles'
import { store } from './store'

import { AuthProvider } from './context/AuthContext'
import Rotas from './routes'

function App() {
  return (
    <Provider store={store}>
      <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <GlobalCss />
          <Rotas />
        </AuthProvider>
      </Router>
    </Provider>
  )
}

export default App
