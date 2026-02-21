import { styled } from 'styled-components'
import { Link } from 'react-router-dom'

import { color } from '../../styles'
import { fadeInDropDown, fadeInIcon } from '../../utils/keyframes'

export const NavbarContainer = styled.div`
  width: 100%;
  height: 70px;
  background-color: ${color.logoSecundary};
  display: flex;
  justify-content: center;
  align-items: center;
`

export const NavbarRow = styled.nav`
  display: flex;
  width: 100%;
  height: 65%;
  justify-content: space-evenly;
`

export const Item = styled.div`
  margin-right: 8px;
  display: flex;
  align-items: center;

  &:hover {
    transform: scale(0.95);
  }
`

export const ItemLink = styled(Link)`
  color: ${color.logoPrimary};
  font-size: 16px;
  display: flex;
  align-items: start;
`

export const NavButton = styled.button`
  color: ${color.logoPrimary};
  background-color: transparent;
  border: none;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  position: relative;

  #imoveis-icon {
    opacity: 0;
    position: absolute;
    right: -16px;
    top: 10px;
  }
  #imoveis-icon.active {
    animation: ${fadeInIcon} 0.6s ease forwards;
  }

  #condominios-icon {
    opacity: 0;
    position: absolute;
    right: -16px;
    top: 10px;
  }
  #condominios-icon.active {
    animation: ${fadeInIcon} 0.6s ease forwards;
  }

  #permutas-icon {
    opacity: 0;
    position: absolute;
    right: -16px;
    top: 10px;
  }
  #permutas-icon.active {
    animation: ${fadeInIcon} 0.6s ease forwards;
  }

  #clientes-icon {
    opacity: 0;
    position: absolute;
    right: -16px;
    top: 10px;
  }
  #clientes-icon.active {
    animation: ${fadeInIcon} 0.6s ease forwards;
  }
`

export const ItemAnimation = styled.div`
  width: 90%;
  display: flex;
  justify-content: center;
  padding: 1px;
  border-radius: 1px;
  background: linear-gradient(currentColor 0 0) var(--p, 0) 100% / var(--d, 0)
    1.45px no-repeat;
  transition:
    0.4s,
    background-position 0s 0.4s;
  &:hover {
    --d: 100%;
    --p: 100%;
  }
`

export const DropDown = styled.div`
  position: absolute;
  top: 30px;
  left: -1px;
  border: 1px solid ${color.logoPrimary};
  display: none;

  &.active {
    display: block;
    animation: ${fadeInDropDown} 0.6s ease forwards;
  }
`

export const DropDownItem = styled.li`
  background-color: ${color.logoSecundary};
  width: 100px;
  padding: 12px;
  border: 0.1px solid ${color.logoPrimary};
  transition: all 0.3s ease;

  ${ItemLink} {
    font-size: 14px;
  }

  &:hover {
    background-color: ${color.logoPrimary};

    ${ItemLink} {
      color: ${color.logoSecundary};
    }
  }
`
