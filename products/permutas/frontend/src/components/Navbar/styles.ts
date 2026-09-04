import { styled } from 'styled-components'
import { Link } from 'react-router-dom'
import { color, radius, spacing, breakpoints } from '../../styles'
import { fadeInDropDown, fadeInIcon } from '../../utils/keyframes'

export const NavbarContainer = styled.div`
  width: 100%;
  height: 56px;
  background: ${color.navbar};
  display: flex;
  justify-content: center;
  align-items: center;
  margin: 0 auto;
  padding: 0;
  position: sticky;
  top: 0;
  z-index: 1000;
`

export const NavbarRow = styled.nav`
  display: flex;
  width: 100%;
  max-width: 1200px;
  height: 100%;
  justify-content: center;
  align-items: center;
  gap: ${spacing.xs};
  padding: 0 ${spacing.lg};

  @media (max-width: ${breakpoints.tablet}) {
    justify-content: space-between;
    padding: 0 ${spacing.md};
  }
`

export const DesktopMenu = styled.div`
  display: flex;
  align-items: center;
  height: 100%;
  gap: ${spacing.xs};

  @media (max-width: ${breakpoints.tablet}) {
    display: none;
  }
`

export const HamburgerButton = styled.button`
  display: none;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: ${spacing.sm};
  color: ${color.navbarText};
  font-size: 24px;
  line-height: 1;

  @media (max-width: ${breakpoints.tablet}) {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  &:hover {
    opacity: 0.7;
  }
`

export const MobileMenu = styled.div<{ $isOpen: boolean }>`
  display: none;
  position: fixed;
  top: 56px;
  left: 0;
  right: 0;
  background: ${color.navbar};
  flex-direction: column;
  padding: ${spacing.md};
  z-index: 999;
  transform: translateY(${props => props.$isOpen ? '0' : '-100%'});
  opacity: ${props => props.$isOpen ? '1' : '0'};
  visibility: ${props => props.$isOpen ? 'visible' : 'hidden'};
  pointer-events: ${props => props.$isOpen ? 'auto' : 'none'};
  transition: transform 0.3s ease, opacity 0.3s ease, visibility 0.3s ease;
  box-shadow: 0 4px 20px ${color.shadowMedium};

  @media (max-width: ${breakpoints.tablet}) {
    display: flex;
  }
`

export const MobileMenuOverlay = styled.div<{ $isOpen: boolean }>`
  display: none;
  position: fixed;
  top: 56px;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 998;
  opacity: ${props => props.$isOpen ? '1' : '0'};
  visibility: ${props => props.$isOpen ? 'visible' : 'hidden'};
  pointer-events: ${props => props.$isOpen ? 'auto' : 'none'};
  transition: opacity 0.3s ease, visibility 0.3s ease;

  @media (max-width: ${breakpoints.tablet}) {
    display: block;
  }
`

export const MobileMenuItem = styled(Link)`
  color: ${color.navbarText};
  font-size: 16px;
  font-weight: 400;
  padding: ${spacing.md};
  text-decoration: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  transition: background 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  &:last-child {
    border-bottom: none;
  }
`

export const MobileMenuButton = styled.button`
  color: ${color.navbarText};
  font-size: 16px;
  font-weight: 400;
  padding: ${spacing.md};
  text-decoration: none;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }
`

export const Logo = styled(Link)`
  color: ${color.navbarText};
  font-size: 16px;
  font-weight: 600;
  text-decoration: none;
  display: none;

  @media (max-width: ${breakpoints.tablet}) {
    display: block;
  }
`

export const Item = styled.div`
  display: flex;
  align-items: center;
  position: relative;
  height: 100%;
`

export const ItemLink = styled(Link)`
  color: ${color.navbarText};
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.02em;
  text-decoration: none;
  display: flex;
  align-items: center;
  padding: ${spacing.sm} ${spacing.md};
  transition: opacity 0.2s ease;

  &:hover {
    opacity: 0.3;
  }
`

export const NavButton = styled.button`
  color: ${color.navbarText};
  background-color: transparent;
  border: none;
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.02em;
  cursor: pointer;
  display: flex;
  align-items: center;
  position: relative;
  padding: ${spacing.sm} ${spacing.md};
  transition: opacity 0.2s ease;
  height: 100%;
  text-decoration: none;

  &:hover {
    opacity: 0.7;
  }

  #imoveis-icon,
  #condominios-icon,
  #permutas-icon,
  #clientes-icon {
    opacity: 0;
    margin-left: 6px;
    color: ${color.navbarText};
  }

  #imoveis-icon.active,
  #condominios-icon.active,
  #permutas-icon.active,
  #clientes-icon.active {
    animation: ${fadeInIcon} 0.3s ease forwards;
  }
`

export const ItemAnimation = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
`

export const DropDown = styled.div`
  position: absolute;
  top: calc(100% - 4px);
  left: 50%;
  transform: translateX(-50%);
  background: ${color.cardBg};
  border: 1px solid ${color.border};
  border-radius: ${radius.lg};
  box-shadow: 0 4px 20px ${color.shadowMedium};
  display: none;
  min-width: 160px;
  padding: ${spacing.sm};
  z-index: 1001;

  &.active {
    display: block;
    animation: ${fadeInDropDown} 0.2s ease forwards;
  }
`

export const AppShell = styled.div`
  width: 100%;
  min-height: 100vh;
  margin: 0;
  padding: 0;
`

export const DropDownItem = styled.li`
  border-radius: ${radius.md};
  transition: all 0.2s ease;

  ${ItemLink} {
    font-size: 13px;
    padding: ${spacing.sm} ${spacing.md};
    width: 100%;
    color: ${color.text};
    border-radius: ${radius.md};
  }

  &:hover {
    background-color: ${color.primary};

    ${ItemLink} {
      color: ${color.textInverse};
    }
  }
`
