import { useContext, useState, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'

import {
  AppShell,
  Item,
  ItemAnimation,
  ItemLink,
  NavButton,
  NavbarContainer,
  NavbarRow,
  DesktopMenu,
  HamburgerButton,
  MobileMenu,
  MobileMenuOverlay,
  MobileMenuItem,
  MobileMenuButton,
  Logo
} from './styles'

import AuthContext from '../../context/AuthContext'

type Props = {
  children: JSX.Element
}

const Navbar = ({ children }: Props) => {
  const { logoutUser } = useContext(AuthContext)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const location = useLocation()

  const handleLogout = () => {
    logoutUser()
    setMobileMenuOpen(false)
  }

  const toggleMobileMenu = () => {
    setMobileMenuOpen(!mobileMenuOpen)
  }

  const closeMobileMenu = useCallback(() => {
    setMobileMenuOpen(false)
  }, [])

  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [mobileMenuOpen])

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileMenuOpen) {
        closeMobileMenu()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [mobileMenuOpen, closeMobileMenu])

  return (
    <>
      <NavbarContainer>
        <NavbarRow>
          <Logo to="/home">ONE</Logo>
          
          <DesktopMenu>
            <Item>
              <ItemLink to="/home">
                <ItemAnimation>Home</ItemAnimation>
              </ItemLink>
            </Item>
            <Item>
              <ItemLink to="/matches">
                <ItemAnimation>Matches</ItemAnimation>
              </ItemLink>
            </Item>
            <Item>
              <ItemLink to="/imoveis">
                <ItemAnimation>Imóveis</ItemAnimation>
              </ItemLink>
            </Item>
            <Item>
              <ItemLink to="/permutas">
                <ItemAnimation>Permutas</ItemAnimation>
              </ItemLink>
            </Item>
            <Item>
              <ItemLink to="/clientes">
                <ItemAnimation>Clientes</ItemAnimation>
              </ItemLink>
            </Item>
            <Item>
              <ItemLink to="/condominios">
                <ItemAnimation>Condomínios</ItemAnimation>
              </ItemLink>
            </Item>
            <Item>
              <ItemLink to="/corretores">
                <ItemAnimation>Corretores</ItemAnimation>
              </ItemLink>
            </Item>
            <Item>
              <NavButton onClick={handleLogout}>
                <ItemAnimation>Logout</ItemAnimation>
              </NavButton>
            </Item>
          </DesktopMenu>

          <HamburgerButton 
            onClick={toggleMobileMenu} 
            aria-label={mobileMenuOpen ? 'Fechar menu' : 'Abrir menu'}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-menu"
          >
            {mobileMenuOpen ? '✕' : '☰'}
          </HamburgerButton>
        </NavbarRow>
      </NavbarContainer>

      <MobileMenuOverlay 
        $isOpen={mobileMenuOpen} 
        onClick={closeMobileMenu}
        aria-hidden={!mobileMenuOpen}
      />
      <MobileMenu 
        $isOpen={mobileMenuOpen}
        id="mobile-menu"
        aria-hidden={!mobileMenuOpen}
        role="navigation"
      >
        <MobileMenuItem to="/home" onClick={closeMobileMenu} tabIndex={mobileMenuOpen ? 0 : -1}>Home</MobileMenuItem>
        <MobileMenuItem to="/matches" onClick={closeMobileMenu} tabIndex={mobileMenuOpen ? 0 : -1}>Matches</MobileMenuItem>
        <MobileMenuItem to="/imoveis" onClick={closeMobileMenu} tabIndex={mobileMenuOpen ? 0 : -1}>Imóveis</MobileMenuItem>
        <MobileMenuItem to="/permutas" onClick={closeMobileMenu} tabIndex={mobileMenuOpen ? 0 : -1}>Permutas</MobileMenuItem>
        <MobileMenuItem to="/clientes" onClick={closeMobileMenu} tabIndex={mobileMenuOpen ? 0 : -1}>Clientes</MobileMenuItem>
        <MobileMenuItem to="/condominios" onClick={closeMobileMenu} tabIndex={mobileMenuOpen ? 0 : -1}>Condomínios</MobileMenuItem>
        <MobileMenuItem to="/corretores" onClick={closeMobileMenu} tabIndex={mobileMenuOpen ? 0 : -1}>Corretores</MobileMenuItem>
        <MobileMenuButton onClick={handleLogout} tabIndex={mobileMenuOpen ? 0 : -1}>Logout</MobileMenuButton>
      </MobileMenu>

      <AppShell>
        {children}
      </AppShell>
    </>
  )
}

export default Navbar
